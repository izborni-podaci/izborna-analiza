"""RIK's station tables for rounds before its results app (2022 and earlier), in the CSV layout RIK exports today.

Those rounds were published as Excel tables with one row per polling station ("Табела 3, по бирачким
местима"): registered voters, voters who signed, ballots in the box, invalid and valid ballots, then each
contestant's votes. Station names and minutes aren't in them, so those columns stay empty."""

from __future__ import annotations

import re

from izbori.appdata import region_code, to_csv

HEADERS = [  # header text, lowercased, starts with → field; more specific first
    ("назив округа", "district_name"), ("округ", "district"), ("назив општине", "municipality"),
    ("општина", "code"), ("рбр", "number"), ("уписан", "registered"), ("изашл", "voted"),
    ("број бирача који су гласали", "ballots"), ("неважећ", "invalid"), ("важећ", "valid"),
]


def field_of(header) -> str | None:
    h = " ".join(str(header).split()).lower()
    return next((field for start, field in HEADERS if h.startswith(start)), None)


def number(value) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value or "").strip().replace(".", "")
    return int(s) if s.isdigit() else None


def read_xls(data: bytes) -> list[list]:
    import xlrd
    sheet = xlrd.open_workbook(file_contents=data).sheet_by_index(0)
    return [sheet.row_values(i) for i in range(sheet.nrows)]


def table_rows(rows: list[list], known: dict[str, tuple[str, str]]) -> tuple[bytes, dict]:
    """The table as RIK's CSV, and a summary. known: municipality code → (district, district code) from a
    newer round, so stations group the same way as there."""
    at = next(i for i, r in enumerate(rows) if any(field_of(c) == "number" for c in r))
    cols: dict[str, int] = {}
    names: list[tuple[int, str]] = []
    for j, h in enumerate(rows[at]):
        field = field_of(h)
        if field and field not in cols:
            cols[field] = j
        elif "valid" in cols and str(h).strip():
            names.append((j, " ".join(str(h).split()).title()))
    missing = {"code", "number", "registered", "voted", "ballots", "invalid", "valid"} - set(cols)
    if missing or not names:
        raise ValueError(f"table header not recognised: missing {sorted(missing)}")
    out = []
    for r in rows[at + 1:]:
        r = list(r) + [""] * (len(rows[at]) - len(r))
        code, n = number(r[cols["code"]]), number(r[cols["number"]])
        if code is None or n is None:
            continue
        district_name = str(r[cols["district_name"]]).strip() if "district_name" in cols else ""
        district, district_code = known.get(str(code)) or (district_name, region_code(district_name))
        row = {"bm_uid": f"{code}-{n}", "bm_broj": n, "bm_naziv": "", "sifra_opstine": code,
               "opstina": str(r[cols["municipality"]]).strip() if "municipality" in cols else "",
               "okrug_region": district, "sifra_okruga_regiona": district_code,
               "upisani_biraci": number(r[cols["registered"]]), "glasali_biraci": number(r[cols["voted"]]),
               "listici_u_kutiji": number(r[cols["ballots"]]), "vazeci_glasovi": number(r[cols["valid"]]),
               "nevazeci_listici": number(r[cols["invalid"]]), "vreme_unosa_rezultata": "",
               "zapisnik_link": "", "korekcija_dokument_link": ""}
        for k, (j, _) in enumerate(names, start=1):
            row[f"lista_{k}"] = number(r[j]) or 0
        out.append(row)
    info = {"contestants": [{"name": name} for _, name in names], "stations": len(out)}
    return to_csv(out, len(names)), info


def rik_time(url: str) -> str | None:
    """RIK's file names end with the time they were made, e.g. ..._17_04_2022_01h16.XLS."""
    m = re.search(r"(\d{2})_(\d{2})_(\d{4})_(\d{2})h(\d{2})", url)
    return f"{m[1]}.{m[2]}.{m[3]} {m[4]}:{m[5]}:00" if m else None
