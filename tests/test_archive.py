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
    assert ("70000/2", "minutes_replaced") in flags
    assert ("70000/3", "correction_unapplied") in flags


def test_history_flags_compare_the_same_station(tmp_path):
    a = new_archive(tmp_path)
    stations = [station(str(i), registered=500, voted=300) for i in range(1, 21)]
    a.add_snapshot("1", make_csv(stations), fetched="2026-10-25T20:00:00+00:00")
    a.save_meta("2", {"kind": "presidential", "title": "Later", "contestants": [{"name": "А"}, {"name": "Б"}]})
    later = [station(str(i), registered=500, voted=300) for i in range(1, 19)]
    later.append(station("19", registered=620, voted=300))  # register jump
    later.append(station("20", registered=500, voted=460, l1=360, l2=95))  # turnout 60% -> 92%
    a.add_snapshot("2", make_csv(later), fetched="2026-12-20T20:00:00+00:00")
    rnd = a.load("2")
    flags = {(f.station, f.code) for f in station_flags(rnd, previous=[a.load("1")])}
    assert ("70000/19", "register_jump") in flags
    assert ("70000/20", "turnout_jump") in flags
    assert not any(s == "70000/5" for s, _ in flags)
