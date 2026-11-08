"""The coordinator's page: similar municipalities, deviations of a list by station, the weak-spot cards."""
from izbori import coordinator
from izbori.checks import Flag
from izbori.settlements import Figures

from test_archive import make_csv, new_archive, station


def test_size_class_and_similar_municipalities():
    assert [coordinator.size_class(n) for n in (100, 5000, 14999, 40000, 250000)] == [0, 1, 1, 3, 4]
    rows = {str(k): {"kind": "domestic", "registered": 8000, "counted": 10, "turnout": 0.5 + k / 100,
                     "invalid": 0.02, "flagged_share": 0.1} for k in range(8)}
    rows["big"] = {"kind": "domestic", "registered": 90000, "counted": 50, "turnout": 0.9, "invalid": 0.01,
                   "flagged_share": 0.0}
    rows["abroad"] = {"kind": "abroad", "registered": 8000, "counted": 1, "turnout": 0.1, "invalid": 0.0,
                      "flagged_share": 0.0}
    profiles = {c: {"size": coordinator.size_class(m["registered"]), "urban": None} for c, m in rows.items()
                if m["kind"] == "domestic"}
    sim = coordinator.similar("0", profiles, rows)
    assert sim["n"] == 7 and abs(sim["turnout"] - (0.5 + sum(range(1, 8)) / 700)) < 1e-9  # the others of its size
    assert coordinator.similar("big", profiles, rows) is None  # nobody its size
    # a town is compared with towns when the kind is known on both sides
    profiles["0"]["urban"] = True
    profiles["1"]["urban"] = profiles["2"]["urban"] = False
    assert coordinator.similar("0", profiles, rows)["n"] == 5  # 3..7 unknown kind count, 1 and 2 are rural
    profiles["3"]["urban"] = False
    assert coordinator.similar("0", profiles, rows) is None  # four left: too few to say anything


def test_urban_share_needs_half_the_stations_placed(tmp_path):
    a = new_archive(tmp_path)
    a.add_snapshot("1", make_csv([station(str(i)) for i in range(1, 5)]), fetched="2026-10-25T20:00:00+00:00")
    sts = a.load("1").stations
    figures = {("Тест", "Град"): Figures(urban=True, pop2011=1000, pop2022=1000),
               ("Тест", "Село"): Figures(urban=False, pop2011=100, pop2022=90)}
    joined = {"70000/1": {"u": "Тест", "s": "Град"}, "70000/2": {"u": "Тест", "s": "Село"}}
    assert coordinator.urban_share(sts, joined, figures) == 0.5
    assert coordinator.urban_share(sts, {"70000/1": {"u": "Тест", "s": "Град"}}, figures) is None


def test_deviations_against_the_rest(tmp_path):
    a = new_archive(tmp_path)
    sts = [station("1", voted=100, l1=80, l2=20, invalid=0), station("2", voted=100, l1=50, l2=50, invalid=0),
           station("3", voted=100, l1=10, l2=90, invalid=0)]
    a.add_snapshot("1", make_csv(sts), fetched="2026-10-25T20:00:00+00:00")
    rnd = a.load("1")
    counted = [s for s in rnd.stations if s.counted]
    votes = [sum(s.votes[i] for s in counted) for i in range(2)]
    rows = coordinator.deviations(rnd.stations, votes, 0)
    assert [r["s"].number for r in rows] == ["3", "1", "2"]  # largest difference first
    assert abs(rows[1]["dev"] - (0.8 - 60 / 200)) < 1e-9 and abs(rows[2]["dev"] - (0.5 - 90 / 200)) < 1e-9


def test_weak_spots(tmp_path):
    a = new_archive(tmp_path)
    sts = [station(str(i), registered=500, voted=300) for i in range(1, 6)]
    a.add_snapshot("1", make_csv(sts), fetched="2026-10-25T20:00:00+00:00")
    rnd = a.load("1")
    by_key = {s.key: s for s in rnd.stations}
    flags_of = {
        "70000/1": [Flag("70000/1", "near_unanimity", {})],
        "70000/2": [Flag("70000/2", "registered_jump", {"growth": 0.2}), Flag("70000/2", "remark_filed", {})],
        "70000/3": [Flag("70000/3", "turnout_apart", {"now": 0.9, "base": 0.6})],
        "70000/4": [Flag("70000/4", "remark_filed", {})],
    }
    ctrl = {"70000/1": {"lists": {"1": {"member": "A"}, "2": {}}}, "70000/2": {"lists": {"1": {}, "2": {"deputy": "B"}}},
            "70000/3": {"lists": {"1": {"deputy": "C"}, "2": {}}}}

    class R:
        remarks = True
    weak = coordinator.weak_spots(rnd.stations, flags_of, [], {}, ctrl, 2, lambda s: "Село" if s.number in ("1", "3") else "",
                                  {"70000/3": R()})
    assert [s.number for s in weak["unanimous"]] == ["1"]
    assert [s.number for s in weak["without"]] == ["1", "3"] and weak["ctrl_read"] == 3
    assert weak["without_groups"] == [("Село", [by_key["70000/1"], by_key["70000/3"]])]
    assert [s.number for s in weak["register"]] == ["2"] and [s.number for s in weak["apart"]] == ["3"]
    # station 1 stands out with nobody asking; 2 has a remark filed, 3 a reviewed remark, 4 only a records flag
    assert [s.number for s in weak["silent"]] == ["1"]
    assert coordinator.controller_of(ctrl["70000/2"], 2) == "deputy" and coordinator.controller_of(None, 1) is None
    data = coordinator.station_json(rnd.stations, ctrl, flags_of, lambda s: "", 2, {s.key: "x" for s in rnd.stations})
    assert data[0]["ctrl"] == "mn" and data[1]["ctrl"] == "nd" and data[4]["ctrl"] is None
    assert data[0]["flags"] == ["near_unanimity"] and data[0]["v"] == list(by_key["70000/1"].votes)
