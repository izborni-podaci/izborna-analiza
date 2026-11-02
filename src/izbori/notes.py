"""News notes: a news report about one polling station, added by hand. A note is never a flag.

notes/<round>.csv, one row per report:
municipality_code, station, date, outlet, url, archive_url, summary_sr, summary_en
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

FIELDS = ["municipality_code", "station", "date", "outlet", "url", "archive_url", "summary_sr", "summary_en"]


@dataclass
class Note:
    municipality_code: str
    station: str
    date: str
    outlet: str
    url: str
    archive_url: str
    summary_sr: str
    summary_en: str

    @property
    def key(self) -> str:
        return f"{self.municipality_code}/{self.station}"

    def summary(self, loc: str) -> str:
        return (self.summary_en if loc == "en" else self.summary_sr) or self.summary_sr or self.summary_en


def load_notes(notes_dir: Path, rid: str) -> dict[str, list[Note]]:
    path = Path(notes_dir) / f"{rid}.csv"
    out: dict[str, list[Note]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not (row.get("municipality_code") or "").strip():
                continue
            if not (row.get("url") or "").startswith(("https://", "http://")):
                continue
            note = Note(**{k: (row.get(k) or "").strip() for k in FIELDS})
            out.setdefault(note.key, []).append(note)
    return out


def write_template(notes_dir: Path, rid: str) -> Path:
    path = Path(notes_dir) / f"{rid}.csv"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(FIELDS)
    return path
