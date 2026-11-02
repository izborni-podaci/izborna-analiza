"""Read RIK's results CSV. Works for any election type: contestant columns are found by position."""

from __future__ import annotations

import csv
import io

from izbori.model import Station

HEAD = [
    "bm_uid", "bm_broj", "bm_naziv", "opstina", "sifra_opstine", "okrug_region",
    "sifra_okruga_regiona", "upisani_biraci", "glasali_biraci", "listici_u_kutiji",
    "vazeci_glasovi", "nevazeci_listici", "vreme_unosa_rezultata",
]
TAIL = ["zapisnik_link", "korekcija_dokument_link"]
NUMBERS = ["upisani_biraci", "glasali_biraci", "listici_u_kutiji", "vazeci_glasovi", "nevazeci_listici"]


class FormatError(ValueError):
    """RIK's file doesn't have the columns this tool expects."""


def decode(raw: bytes) -> str:
    return raw.decode("utf-8-sig")


def read_rows(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(decode(raw)))
    columns = [c.strip() for c in (reader.fieldnames or [])]
    reader.fieldnames = columns
    missing = [c for c in HEAD + TAIL if c not in columns]
    if missing:
        raise FormatError(f"RIK file is missing columns {missing}; found {columns}")
    return columns, list(reader)


def contestant_columns(columns: list[str]) -> list[str]:
    """Columns between the entry time and the minutes link hold one contestant each, in ballot order."""
    start = columns.index("vreme_unosa_rezultata") + 1
    end = columns.index("zapisnik_link")
    return columns[start:end]


def _int(value: str | None) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    return int(value.replace(".", "").replace(" ", ""))


def parse(raw: bytes, n_contestants: int | None = None) -> tuple[list[Station], int]:
    """Return the stations and the number of contestants.

    RIK's file always has a fixed number of contestant columns (30 in 2026) and fills the unused ones
    with zeros. When the number isn't known from RIK's summary, the last column with any vote decides.
    """
    columns, rows = read_rows(raw)
    vote_cols = contestant_columns(columns)
    stations = []
    for r in rows:
        votes = [_int(r.get(c)) for c in vote_cols]
        stations.append(Station(
            key=f"{r['sifra_opstine'].strip()}/{r['bm_broj'].strip()}",
            uid=r["bm_uid"].strip(),
            number=r["bm_broj"].strip(),
            name=r["bm_naziv"].strip(),
            municipality=r["opstina"].strip(),
            municipality_code=r["sifra_opstine"].strip(),
            district=r["okrug_region"].strip(),
            district_code=r["sifra_okruga_regiona"].strip(),
            registered=_int(r["upisani_biraci"]),
            voted=_int(r["glasali_biraci"]),
            ballots=_int(r["listici_u_kutiji"]),
            valid=_int(r["vazeci_glasovi"]),
            invalid=_int(r["nevazeci_listici"]),
            entered=r["vreme_unosa_rezultata"].strip(),
            votes=votes,
            minutes=r["zapisnik_link"].strip(),
            correction=r["korekcija_dokument_link"].strip(),
        ))
    if n_contestants is None:
        n_contestants = 0
        for s in stations:
            for i, v in enumerate(s.votes):
                if v and i + 1 > n_contestants:
                    n_contestants = i + 1
    for s in stations:
        s.votes = s.votes[:n_contestants]
    return stations, n_contestants
