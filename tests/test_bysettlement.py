"""Results and controllers by kind of settlement: the classes, the sums, the comparison within municipalities, and the
same rules for every contestant."""

from izbori import bysettlement as B
from izbori import settlements as S
from izbori.model import Contestant, Station

# two municipalities: one with a town and a village, one with villages only
FIG = {("A", "Town"): S.Figures(True, 20000, 18000, 3000), ("A", "Village"): S.Figures(False, 1000, 700, 280),
       ("B", "Hamlet"): S.Figures(False, 400, 250, 120)}


def station(code, number, votes, registered=100):
    valid = sum(votes)
    return Station(key=f"{code}/{number}", uid="", number=str(number), name="", municipality=code,
                   municipality_code=code, district="D", district_code="1", registered=registered, voted=valid,
                   ballots=valid, valid=valid, invalid=0, entered="", votes=list(votes))


def contestants(n=2):
    return [Contestant(number=i + 1, name=f"List {i + 1}", short="") for i in range(n)]


def setup():
    stations = [station("1", 1, [60, 40]), station("1", 2, [20, 30]), station("1", 3, [10, 40]),
                station("2", 1, [5, 45]), station("2", 2, [9, 1])]
    joined = {"1/1": {"u": "A", "s": "Town", "m": "address"}, "1/2": {"u": "A", "s": "Town", "m": "address"},
              "1/3": {"u": "A", "s": "Village", "m": "station"}, "2/1": {"u": "B", "s": "Hamlet", "m": "single"}}
    ctrl = {"1/1": {"lists": {"1": {"member": True}}}, "1/2": {"lists": {"1": {"deputy": True}, "2": {"member": True}}},
            "1/3": {"lists": {"2": {"member": True}}}, "2/1": {"lists": None}}
    return stations, joined, ctrl


def test_classes_run_from_their_bound():
    assert [B.klass(v, B.SIZE) for v in (0, 499, 500, 1999, 2000, 99999, 100000)] == [0, 0, 1, 1, 2, 3, 4]
    assert [B.klass(v, B.CHANGE) for v in (-0.5, -0.2000001, -0.2, -0.1, -0.05, 0.0, 0.3)] == [0, 0, 1, 2, 2, 3, 3]
    assert B.klass(None, B.SIZE) is None
    assert B.classes_of(FIG[("A", "Village")]) == {"type": 1, "size": 1, "change": 0}


def test_shares_coverage_and_the_difference_within_municipalities():
    stations, joined, ctrl = setup()
    r = B.analyse(stations, contestants(), joined, FIG, ctrl)
    assert r["used"] == 4 and r["without"] == {"none": 1} and r["how"] == {"address": 2, "station": 1, "single": 1}
    assert r["municipalities_both"] == 1
    urban, other = r["groups"]["type"]
    assert (urban.stations, len(urban.places), other.stations, len(other.places)) == (2, 1, 2, 2)
    by = {row["number"]: row for row in r["rows"]}
    assert [row["number"] for row in r["rows"]] == [2, 1]  # most votes in the whole election first
    assert by[1]["votes"]["type"] == [80 / 150, 15 / 100]
    # within municipality 1: other (station 3) minus urban (stations 1 and 2), the smaller side weighing 1
    assert abs(by[1]["votes_within"] - (10 / 50 - 80 / 150)) < 1e-12
    # controllers: read decisions only (Hamlet's wasn't read), shown where at least 10 and half were read
    assert (urban.read, other.read, urban.covered, other.covered) == (2, 1, [2, 1], [0, 1])
    assert by[1]["ctrl"]["type"] == [None, None] and not r["controllers"]
    assert by[1]["ctrl_within"] == 0 - 1  # village 0 of 1, town 2 of 2
    lines = B.to_csv(r, contestants()).splitlines()
    assert lines[0].startswith("dimension,class,number,contestant,stations")
    assert "type,urban,1,List 1,2,1,200,150,150,80,0.533333,2,2,1.0" in lines


def test_the_same_rules_for_every_contestant():
    stations, joined, ctrl = setup()
    swapped = [station(s.municipality_code, s.number, list(reversed(s.votes))) for s in stations]
    ctrl_swapped = {k: {"lists": None if v["lists"] is None else {str(3 - int(n)): x for n, x in v["lists"].items()}}
                    for k, v in ctrl.items()}
    a = B.analyse(stations, contestants(), joined, FIG, ctrl)
    b = B.analyse(swapped, contestants(), joined, FIG, ctrl_swapped)
    for row in a["rows"]:
        twin = next(x for x in b["rows"] if x["number"] == 3 - row["number"])
        assert (row["votes"], row["votes_within"], row["ctrl_within"]) == (twin["votes"], twin["votes_within"],
                                                                         twin["ctrl_within"])


def test_2026_by_settlement(archive, round2026):
    from izbori import boards
    joined = S.load_store(archive.dir("680072"))["stations"]
    fig = S.load_figures(archive.root)
    ctrl = boards.coverage(boards.load_store(archive.dir("680072")))
    r = B.analyse(round2026.stations, round2026.contestants, joined, fig, ctrl)
    assert r["used"] == sum(1 for s in round2026.stations if s.key in joined and s.counted)
    for d in B.DIMENSIONS[:2]:  # every station has a type and a size
        assert sum(c["stations"] for c in r["classes"][d]) == r["used"]
    assert r["controllers"] and r["municipalities_both"] > 100
    totals = [sum(s.votes[i] or 0 for s in round2026.stations if s.counted) for i in range(len(round2026.contestants))]
    assert [row["index"] for row in r["rows"]] == sorted(range(len(totals)), key=lambda i: -totals[i])
