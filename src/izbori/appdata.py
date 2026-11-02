"""Rebuild a round's results file from RIK's results app, one polling station at a time.

For finished rounds RIK no longer offers the CSV export, but its results app still answers per station:
registered voters, voters, valid and invalid ballots, each contestant's votes and the minutes. This module
asks for every station and writes the same CSV layout RIK exports, so the archive and the checks work
unchanged. Ballots in the box aren't reported separately there, so that column is valid + invalid."""

from __future__ import annotations

import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor
from html import unescape

from izbori.boards import municipality_key
from izbori.load import HEAD, TAIL
from izbori.rik import RikError, _int

REGION_CODES = [("Београд", "RS11"), ("Војводин", "RS12"), ("Шумадиј", "RS21"), ("Јужне", "RS22"),
                ("Косов", "RS23"), ("Завод", "/55001"), ("Иностран", "/33000")]
PUBLIC = "https://www.rik.parlament.gov.rs"


def region_code(name: str) -> str:
    return next((code for key, code in REGION_CODES if key in name), "")


def minutes_field(html: str) -> tuple[str, str]:
    """RIK's minutes block as "label|url" lines, and the earliest upload time as YYYY-MM-DD HH:MM:00."""
    entries, times = [], []
    for m in re.finditer(r"<span>([^<]+)</span></div>\s*<div class='table-file[^']*'><a href='([^']+)'[^>]*>.*?"
                         r"<span>(\d{2})-(\d{2})-(\d{4}) (\d{2}):(\d{2})h</span>", html or "", re.S):
        label, href = unescape(m.group(1)).strip(), m.group(2)
        url = href if href.startswith("http") else PUBLIC + href
        entries.append(f"{label}|{url}")
        d, mo, y, h, mi = m.group(3), m.group(4), m.group(5), m.group(6), m.group(7)
        times.append(f"{y}-{mo}-{d} {h}:{mi}:00")
    return " \n ".join(entries), (min(times) if times else "")


def station_row(data: dict, n: int, station_id: str, title: str, municipality: str, code: str, region: str,
                region_code_: str) -> dict:
    stat = data.get("stat_sum_numbers") or {}
    valid = invalid = None
    pie = ((data.get("sum_config") or {}).get("data") or {})
    values = ((pie.get("datasets") or [{}])[0].get("data") or [])
    labels = pie.get("labels") or []
    for label, value in zip(labels, values):
        if "Неважећ" in label or "Nevažeć" in label:
            invalid = int(value)
        elif "Важећ" in label or "Važeć" in label:
            valid = int(value)
    votes = {}
    for row in data.get("table_data") or []:
        number = _int(row.get("count_number"))
        if number:
            votes[number] = _int(row.get("won_number")) or 0
    minutes, entered = minutes_field(data.get("minute_from_election_station") or "")
    number, _, name = title.partition("-")
    row = {
        "bm_uid": station_id, "bm_broj": number.strip(), "bm_naziv": name.strip(), "opstina": municipality,
        "sifra_opstine": code, "okrug_region": region, "sifra_okruga_regiona": region_code_,
        "upisani_biraci": _int(stat.get("total_voters")), "glasali_biraci": _int(stat.get("available")),
        "listici_u_kutiji": (valid + invalid) if valid is not None and invalid is not None else None,
        "vazeci_glasovi": valid, "nevazeci_listici": invalid, "vreme_unosa_rezultata": entered,
        "zapisnik_link": minutes, "korekcija_dokument_link": "",
    }
    for k in range(1, n + 1):
        row[f"lista_{k}"] = votes.get(k, 0)
    return row


def to_csv(rows: list[dict], n: int) -> bytes:
    columns = HEAD + [f"lista_{k}" for k in range(1, n + 1)] + TAIL
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: "" if r.get(c) is None else r.get(c) for c in columns})
    return ("﻿" + out.getvalue()).encode("utf-8")


def rebuild(client, rik_type: int, rid: str, codes: dict[str, str], threads: int = 4, log=print) -> tuple[bytes, dict]:
    """The round's results as RIK's CSV, and a summary (title, contestants, RIK's time)."""
    summary = client._json("/get_results/", {"should_update_pies": 0, "type": rik_type, "election_round": rid,
                                             "region": 0, "municipality": 0, "election_station": 0}) or {}
    stat = summary.get("stat_sum_numbers") or {}
    contestants = []
    for row in summary.get("table_data") or []:
        name = re.sub(r"^\s*\d+\s*[.)]\s*", "", str(row.get("list_name") or "")).strip()
        contestants.append((_int(row.get("count_number")) or len(contestants) + 1, name))
    contestants.sort()
    n = max((c[0] for c in contestants), default=0)
    jobs = []
    for region_id, region_name in client.regions(rik_type, rid).items():
        rc = region_code(region_name)
        for mun_id, mun_name in client.municipalities(rik_type, rid, region_id):
            code = codes.get(municipality_key(mun_name)) or f"r{mun_id}"
            for st_id, title in client.stations(rik_type, rid, region_id, mun_id).items():
                jobs.append((region_id, region_name, rc, mun_id, mun_name, code, st_id, title))
    log(f"{rid}: {len(jobs)} polling stations to fetch")

    def fetch(job):
        region_id, region_name, rc, mun_id, mun_name, code, st_id, title = job
        data = client.station_results(rik_type, rid, region_id, mun_id, st_id)
        return station_row(data, n, st_id, title, mun_name, code, region_name, rc)

    rows, failed = [], []
    with ThreadPoolExecutor(max_workers=threads) as ex:
        futures = [(job, ex.submit(fetch, job)) for job in jobs]
        for k, (job, f) in enumerate(futures, start=1):
            try:
                rows.append(f.result())
            except RikError:
                failed.append(job)
            if k % 1000 == 0:
                log(f"{rid}: {k}/{len(jobs)}")
    for job in failed:  # one more try, one at a time
        rows.append(fetch(job))
    expected = _int(stat.get("number_of_stations"))
    if expected and len(rows) != expected:
        raise RikError(f"{rid}: got {len(rows)} stations, RIK reports {expected}")
    rows.sort(key=lambda r: (str(r["sifra_opstine"]), int(r["bm_broj"]) if str(r["bm_broj"]).isdigit() else 0))
    info = {"title": str(stat.get("election_title") or "").strip(), "rik_time": stat.get("datetime"),
            "contestants": [{"name": name} for _, name in contestants], "stations": len(rows)}
    return to_csv(rows, n), info
