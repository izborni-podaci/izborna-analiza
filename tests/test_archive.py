"""The archive: snapshots, the change log, and the flags that need history."""

import csv
import io

from izbori.checks import station_flags
from izbori.history import Archive

HEADER = ["bm_uid", "bm_broj", "bm_naziv", "opstina", "sifra_opstine", "okrug_region", "sifra_okruga_regiona",
          "upisani_biraci", "glasali_biraci", "listici_u_kutiji", "vazeci_glasovi", "nevazeci_listici",
          "vreme_unosa_rezultata", "lista_1", "lista_2", "zapisnik_link", "korekcija_dokument_link"]
MINUTES = "Записник|https://rik.parlament.gov.rs/extfile/sr/election_results/1/2/6ade9d70be16f/@ПО1_x.pdf"


def make_csv(rows: list[dict]) -> bytes:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=HEADER)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return ("﻿" + out.getvalue()).encode("utf-8")


def station(number: str, registered=500, voted=300, l1=200, l2=95, invalid=5, minutes=MINUTES, correction=""):
    return {"bm_uid": number, "bm_broj": number, "bm_naziv": f"ОШ {number}", "opstina": "Тест",
            "sifra_opstine": "70000", "okrug_region": "Регион/Округ", "sifra_okruga_regiona": "RS11/00",
            "upisani_biraci": registered, "glasali_biraci": voted, "listici_u_kutiji": voted,
            "vazeci_glasovi": l1 + l2, "nevazeci_listici": invalid, "vreme_unosa_rezultata": "2026-12-20 21:00:00",
            "lista_1": l1, "lista_2": l2, "zapisnik_link": minutes, "korekcija_dokument_link": correction}


def new_archive(tmp_path) -> Archive:
    a = Archive(tmp_path / "data")
    a.save_meta("1", {"kind": "presidential", "title": "Test", "contestants": [{"name": "А"}, {"name": "Б"}]})
    return a


def test_identical_file_is_not_archived_twice(tmp_path):
    a = new_archive(tmp_path)
    raw = make_csv([station("1"), station("2")])
    assert a.add_snapshot("1", raw, fetched="2026-12-20T20:00:00+00:00") is not None
    assert a.add_snapshot("1", raw, fetched="2026-12-20T20:03:00+00:00") is None
    assert len(a.snapshots("1")) == 1
    assert set(a.first_seen("1")) == {"70000/1", "70000/2"}


def test_changes_and_change_flags(tmp_path):
    a = new_archive(tmp_path)
    a.add_snapshot("1", make_csv([station("1"), station("2"), station("3")]), fetched="2026-12-20T20:00:00+00:00")
    later = [
        station("1", l1=199, l2=96),  # votes moved
        station("2", minutes=MINUTES.replace("6ade9d70be16f", "6ade9d70be170")),  # minutes replaced
        station("3", correction="Решење (Образац РГ-7-1)|https://rik.parlament.gov.rs/x/@r.pdf"),  # ruling, no change
    ]
    result = a.add_snapshot("1", make_csv(later), fetched="2026-12-20T21:00:00+00:00")
    fields = {(e["s"], e["f"]) for e in result.changes}
    assert ("70000/1", "lista_1") in fields and ("70000/1", "lista_2") in fields
    flags = {(f.station, f.code) for f in station_flags(a.load("1"), a.changes("1"))}
    assert ("70000/1", "changed") in flags
    assert not any(code == "minutes_replaced" for _, code in flags)  # a replaced link is a document, not a warning
    assert ("70000/3", "correction_unapplied") in flags
    from izbori.report import station_documents
    docs = station_documents(a, a.load("1"), a.changes("1"))
    kinds = [d.kind for d in docs["70000/2"]]
    assert kinds == ["minutes", "minutes_previous"], kinds  # the current minutes first, the earlier version after
    assert "6ade9d70be16f" in docs["70000/2"][1].url


def test_history_flags_compare_the_same_station(tmp_path):
    a = new_archive(tmp_path)
    stations = [station(str(i), registered=500, voted=300) for i in range(1, 21)]
    a.add_snapshot("1", make_csv(stations), fetched="2026-10-25T20:00:00+00:00")
    a.save_meta("2", {"kind": "presidential", "title": "Later", "contestants": [{"name": "А"}, {"name": "Б"}]})
    later = [station(str(i), registered=500, voted=300) for i in range(1, 19)]
    later.append(station("19", registered=620, voted=300))  # register jump
    later.append(station("20", registered=500, voted=460, l1=360, l2=95))  # turnout 60% -> 92%
    later[2] = station("3", registered=500, voted=120, l1=80, l2=35)  # turnout 60% -> 24%
    a.add_snapshot("2", make_csv(later), fetched="2026-12-20T20:00:00+00:00")
    rnd = a.load("2")
    flags = {(f.station, f.code) for f in station_flags(rnd, previous=[a.load("1")])}
    assert ("70000/20", "turnout_jump") in flags
    assert ("70000/3", "turnout_drop") in flags and ("70000/3", "turnout_jump") not in flags
    assert not any(code == "register_jump" for _, code in flags)  # registers are compared per municipality
    assert not any(s == "70000/5" for s, _ in flags)
    from izbori.stats import register_changes
    national, rows = register_changes(rnd, a.load("1"), min_registered=0)
    assert rows[0].code == "70000" and rows[0].now == 10120 and rows[0].before == 10000


def test_repeats_across_elections(tmp_path):
    from izbori import repeat
    from izbori.report import analyze
    a = new_archive(tmp_path)
    a.add_snapshot("1", make_csv([station(str(i)) for i in range(1, 11)] + [station("11", invalid=50)]),
                   fetched="2026-10-25T20:00:00+00:00")
    a.save_meta("2", {"kind": "presidential", "title": "Later", "contestants": [{"name": "А"}, {"name": "Б"}]})
    a.add_snapshot("2", make_csv([station(str(i)) for i in range(1, 11)] + [station("11", invalid=50)]),
                   fetched="2026-12-20T20:00:00+00:00")
    analyses = [analyze(a, rid, None, {}) for rid in a.round_ids()]
    rows, once = repeat.stations(analyses)
    assert [r["key"] for r in rows] == ["70000/11"] and once == 0
    assert rows[0]["k"] == 2 and rows[0]["n"] == 2 and ("ballot_mismatch", 2) in rows[0]["same"]
    assert repeat.same_counts(rows)[0][1] == 1


def test_election_date_ignores_a_stray_early_upload():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from izbori.history import election_date

    def minutes(day: int, hour: int) -> str:
        stamp = int(datetime(2023, 12, day, hour, tzinfo=ZoneInfo("Europe/Belgrade")).timestamp())
        return f"Записник|https://rik.parlament.gov.rs/extfile/sr/election_results/1/2/{stamp:08x}00000/@ПО1_x.pdf"

    # one station's minutes went up two days early (as in the 2023 parliamentary file); the rest on the night
    rows = [station("1", minutes=minutes(15, 12))] + [station(str(n), minutes=minutes(17, 21)) for n in range(2, 6)]
    assert election_date(make_csv(rows)) == "2023-12-17"
    # uploads after midnight still belong to election day
    assert election_date(make_csv([station(str(n), minutes=minutes(18, 1)) for n in range(1, 4)])) == "2023-12-17"
