"""The 2022 census tables of the Statistical Office of the Republic of Serbia (RZS), archived as published.

A polling station serves part of a settlement (naselje), and the census counts people by settlement: population, age
and sex, households, families, every census since 1948, dwellings. Education, ethnicity, economic activity and
migration go down only to municipalities and cities, and education also to the type of settlement within each.
`izbori census` downloads the tables listed here into data/census/2022/, by settlement and by municipality, exactly
as the Office published them, and records in sources.json where each came from, its SHA-256, its size and when it
was fetched. A table is written only when its content changed, so git's history stays a record of what the Office
published.

The census is final, so this runs once, by hand: the census workflow, on GitHub's runners, since the development
sandbox can't reach the Office's site. The tables count people; they hold no one's name."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from izbori import jsonfile
from izbori.config import USER_AGENT

BASE = "https://popis2022.stat.gov.rs/media/"
SOURCE = "Statistical Office of the Republic of Serbia (RZS), 2022 Census: https://popis2022.stat.gov.rs/"
PAUSE = 1.0  # seconds between downloads
# An Excel workbook: .xlsx and .xlsm are zip archives, .xls a compound document
SPREADSHEET = (b"PK\x03\x04", b"\xd0\xcf\x11\xe0")


@dataclass(frozen=True)
class Table:
    path: str  # under BASE, as the Office's list of Excel tables links it
    level: str  # "settlements" or "municipalities": the folder it is kept in
    title: str  # what it counts

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def key(self) -> str:
        """Its path in data/census/2022/."""
        return f"{self.level}/{self.name}"

    @property
    def url(self) -> str:
        return BASE + self.path


TABLES = [
    Table("31355/0_ukupan-broj-stanovnika-naselja.xlsx", "settlements", "Total population, by settlement"),
    Table("31356/1_stanovnistvo-prema-starosti-i-polu.xlsx", "settlements", "Population by age and sex, by settlement"),
    Table("31357/2_domacinstva-prema-broju-clanova.xlsx", "settlements",
          "Households by number of members, by settlement"),
    Table("31358/3_porodice-prema-tipu-i-broju-clanova.xlsx", "settlements",
          "Families by type and number of members, by settlement"),
    Table("31418/4_uporedni-pregled-broja-stanovnika-1948-2022.xlsx", "settlements",
          "Population at every census from 1948 to 2022, by settlement"),
    Table("31419/5_uporedni-pregled-broja-domacinstava-1948-2022.xlsx", "settlements",
          "Households at every census from 1948 to 2022, by settlement"),
    Table("31429/t1i.xlsx", "settlements", "Dwellings: number and floor space, by settlement"),
    Table("31359/0_ukupan-broj-stanovnika.xlsx", "municipalities", "Total population, by municipality and city"),
    Table("31360/1_stanovnistvo-prema-nacionalnoj-pripadnosti-i-polu.xlsx", "municipalities",
          "Population by ethnicity and sex"),
    Table("31361/2_stanovnistvo-prema-starosti-i-polu.xlsx", "municipalities", "Population by age and sex"),
    Table("31362/3_stanovnistvo-staro-15-i-vise-godina-prema-skolskoj-spremi-i-polu.xlsx", "municipalities",
          "Population aged 15 and over by educational attainment and sex"),
    Table("31364/5_stanovnistvo-staro-15-i-vise-godina-prema-kompjuterskoj-pismenosti-i-polu.xlsx", "municipalities",
          "Population aged 15 and over by computer literacy and sex"),
    Table("31372/13_stanovnistvo-prema-migratornim-obelezjima.xlsx", "municipalities",
          "Population by migration characteristics"),
    Table("31414/17_stanovnistvo-prema-ekonomskoj-aktivnosti-starosti-i-polu.xlsx", "municipalities",
          "Population by economic activity, age and sex"),
    Table("31417/20_stanovnistvo-staro-15-i-vise-godina-prema-skolskoj-spremi-polu-starosti-i-tipu-naselja.xlsx",
          "municipalities", "Population aged 15 and over by educational attainment, sex, age and type of settlement"),
]


def get(url: str, tries: int = 3, timeout: int = 120) -> bytes:
    """The file at url; a busy server is asked again, a little later each time."""
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - reported by fetch, with the table it was for
            last = e
            if attempt + 1 < tries:
                time.sleep(10 * (attempt + 1))
    raise RuntimeError(str(last))


def spreadsheet(body: bytes) -> bool:
    """An Excel workbook, not the error page a site sends with status 200."""
    return body.startswith(SPREADSHEET)


def sources_path(out: Path) -> Path:
    return out / "sources.json"


def load_sources(out: Path) -> dict:
    p = sources_path(out)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def fetch(out: Path, tables: list[Table] | None = None, opener=None, log=print, pause: float | None = None,
          now: str | None = None) -> tuple[list[str], list[str]]:
    """Download every table (TABLES by default) into out/<level>/<name> and record it in out/sources.json. A table
    whose content is unchanged is left alone, its first fetch time kept. Returns the tables written and those that
    failed; a failure stops nothing else."""
    tables = TABLES if tables is None else tables
    opener = opener or get
    pause = PAUSE if pause is None else pause
    sources = load_sources(out)
    entries: dict = sources.setdefault("tables", {})
    when = now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed: list[str] = []
    failed: list[str] = []
    for i, t in enumerate(tables):
        if i and pause:
            time.sleep(pause)
        try:
            body = opener(t.url)
        except Exception as e:  # noqa: BLE001 - one table failing doesn't stop the others
            log(f"{t.key}: {e}")
            failed.append(t.key)
            continue
        if not spreadsheet(body):
            log(f"{t.key}: not an Excel workbook ({len(body)} bytes)")
            failed.append(t.key)
            continue
        digest = hashlib.sha256(body).hexdigest()
        path = out / t.key
        kept = entries.get(t.key)
        if kept and kept.get("sha256") == digest and path.exists() and path.read_bytes() == body:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        entries[t.key] = {"url": t.url, "title": t.title, "sha256": digest, "bytes": len(body), "fetched": when}
        changed.append(t.key)
        log(f"{t.key}: {len(body):,} bytes")
    if changed:
        sources["source"] = SOURCE
        out.mkdir(parents=True, exist_ok=True)
        sources_path(out).write_text(jsonfile.dumps(sources, "tables"), encoding="utf-8")
    return changed, failed
