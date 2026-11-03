"""Every document RIK publishes for a polling station: the minutes, the observers' record, remarks, corrections
and decisions.

Source: RIK's register of minutes ("Записници"), one record per polling station listing all its documents. The
register gives each document's label, link and upload time; it carries no names, and neither does what is kept
here. The documents themselves name board members and observers, so the site links to them and never copies them.

The results file already carries the minutes and corrections (and, for rounds rebuilt from the results app, every
document). The register adds what RIK's export leaves out: the observers' record (form RG-11), remarks filed with
the minutes, and the decisions annulling a vote (RG-9) or finding that the results can't be determined (RG-8).

Kept per round in data/rounds/<id>/documents.json:
    {"labels": [label, ...], "stations": {"<code>/<number>": [[label index, path, uploaded], ...]},
     "unmatched": [[municipality, number], ...], "counts": {RIK's document type: stations having one}}
where path is the document's path on RIK's site and uploaded its upload time (YYYY-MM-DDTHH:MM, Belgrade)."""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path

from izbori import jsonfile
from izbori.config import RIK_PUBLIC
from izbori.i18n import BELGRADE

FILE = "documents.json"

# Kinds of document, in the order a station's documents are listed. The first rule a label matches decides. The
# decisions on the polling board come from another register (boards.station_docs).
KINDS = ["minutes", "observers", "remark", "correction", "annulled", "undetermined", "audit", "other",
         "board_standing", "board_standing_change", "board_extended", "board_extended_change", "board_refused",
         "board_other"]
BOARD_KINDS = frozenset(k for k in KINDS if k.startswith("board_"))
_RULES = [
    ("remark", ("ПРИМЕДБ", "PRIMEDB")),
    ("observers", ("ПОСМАТРАЧ", "POSMATRAČ", "POSMATRAC")),
    ("annulled", ("РГ-9", "RG-9", "ПОНИШТАВ", "PONIŠTAV")),
    ("undetermined", ("РГ-8", "RG-8", "НЕ МОГУ УТВРДИТИ", "NE MOGU UTVRDITI")),
    ("audit", ("РГ-6", "RG-6", "КОНТРОЛИ ЗАПИСНИКА", "PO UZORKU", "ПО УЗОРКУ")),
    ("correction", ("РГ-7", "RG-7", "ИСПРАВ", "ISPRAV")),
    ("minutes", ("РГ-2", "RG-2", "ЗАПИСНИК", "ZAPISNIK")),
]
_STAMP = re.compile(r"/([0-9a-f]{13})/@")
_ENTRY = re.compile(r"<span>([^<]+)</span></div>\s*<div class='table-file[^']*'><a href='([^']+)'[^>]*>.*?"
                    r"<span>(\d{2})-(\d{2})-(\d{4}) (\d{2}):(\d{2})h</span>", re.S)


def classify(label: str) -> tuple[str, bool]:
    """Kind of document and whether it belongs to a repeated vote, from RIK's label."""
    text = (label or "").upper()
    kind = next((k for k, words in _RULES if any(w in text for w in words)), "other")
    return kind, "ПОНОВ" in text or "PONOV" in text


def form(label: str) -> str:
    """The form's code for corrections and decisions (RG-7-1, RG-9), in Latin; "" for others."""
    m = re.search(r"Р[ГG]-(\d+(?:-\d+)?)", (label or "").upper().replace("RG-", "РГ-"))
    return f"RG-{m.group(1)}" if m and not m.group(1).startswith(("2", "11")) else ""


def path_of(url: str) -> str:
    """A document's path on RIK's site, decoded, so the same document matches whatever host or encoding."""
    return urllib.parse.unquote(urllib.parse.urlsplit(url.strip()).path)


def uploaded_at(url: str) -> str:
    """Upload time from the stamp RIK puts in every document's link (Belgrade time), or ""."""
    m = _STAMP.search(urllib.parse.unquote(url))
    if not m:
        return ""
    return datetime.fromtimestamp(int(m.group(1)[:8], 16), tz=BELGRADE).strftime("%Y-%m-%dT%H:%M")


@dataclass(frozen=True)
class Doc:
    kind: str
    repeat: bool
    label: str
    url: str
    uploaded: str = ""

    @property
    def form(self) -> str:
        return form(self.label)


def doc(label: str, url: str, uploaded: str = "") -> Doc:
    label = " ".join(unescape(label).split())
    url = url if url.startswith("http") else RIK_PUBLIC.rstrip("/") + url
    kind, repeat = classify(label)
    return Doc(kind, repeat, label, url, uploaded or uploaded_at(url))


# --- RIK's register ------------------------------------------------------------------------------


def parse_record(record: dict) -> tuple[str, str, list[Doc]]:
    """One record of the register: (municipality, station number, documents)."""
    html = " ".join(str(f.get("extfile") or "") for f in record.get("extfiles") or [])
    docs = []
    for m in _ENTRY.finditer(html):
        d, mo, y, h, mi = m.group(3), m.group(4), m.group(5), m.group(6), m.group(7)
        docs.append(doc(m.group(1), m.group(2), f"{y}-{mo}-{d}T{h}:{mi}"))
    number = str(record.get("election_station_number") or "").strip()
    return (record.get("municipality") or "").strip(), number, docs


def last_page(pagination_html: str) -> int:
    pages = [int(p) for p in re.findall(r'data-page="(\d+)"', pagination_html or "")]
    return max(pages) if pages else 1


# RIK's numbers for the kinds of document the register adds to the results file: rulings RG-8 and RG-9 (and on a
# repeat vote), the sample audit, observers' records, remarks.
WATCHED_TYPES = (8, 9, 11, 12, 17, 18, 27, 28, 29, 30, 31)


def counts(client, round_id: str, rik_type: int, types=WATCHED_TYPES) -> dict[str, int]:
    """For each kind of document, at how many stations RIK lists one: a cheap check (one or two requests per kind)
    whether anything was added since the register was last read in full."""
    out = {}
    for t in types:
        first = client.register_page(round_id, rik_type, 1, document_type=t) or {}
        pages = last_page(first.get("pagination", ""))
        last = first if pages == 1 else client.register_page(round_id, rik_type, pages, document_type=t) or {}
        out[str(t)] = (pages - 1) * 10 + len(last.get("records") or [])
    return out


def fetch(client, round_id: str, rik_type: int, threads: int = 3, log=print) -> list[tuple[str, str, list[Doc]]]:
    """Every record of the round's register (about one per polling station)."""
    from concurrent.futures import ThreadPoolExecutor

    def page(n: int) -> dict:
        return client.register_page(round_id, rik_type, n) or {}

    first = page(1)
    pages = last_page(first.get("pagination", ""))
    records = list(first.get("records") or [])
    with ThreadPoolExecutor(max_workers=threads) as ex:
        for k, data in enumerate(ex.map(page, range(2, pages + 1)), start=2):
            records.extend(data.get("records") or [])
            if k % 200 == 0:
                log(f"{round_id}: register page {k}/{pages}")
    return [parse_record(r) for r in records]


# --- the per-round store -------------------------------------------------------------------------


def store(records: list[tuple[str, str, list[Doc]]], codes: dict[str, str]) -> dict:
    """What documents.json keeps: per station key, each document's label, path and upload time.

    codes maps a municipality key (boards.municipality_key) to its code in the round's results."""
    from izbori.boards import municipality_key
    labels: list[str] = []
    index: dict[str, int] = {}
    stations: dict[str, list] = {}
    unmatched = []
    for municipality, number, docs in records:
        code = codes.get(municipality_key(municipality))
        if not code or not number:
            if docs:
                unmatched.append([municipality, number])
            continue
        rows = stations.setdefault(f"{code}/{number}", [])
        for d in docs:
            if d.label not in index:
                index[d.label] = len(labels)
                labels.append(d.label)
            row = [index[d.label], path_of(d.url), d.uploaded]
            if row not in rows:
                rows.append(row)
    for rows in stations.values():
        rows.sort(key=lambda r: (r[2], r[1]))
    return {"labels": labels, "stations": dict(sorted(stations.items())), "unmatched": sorted(unmatched)}


def path(round_dir: Path) -> Path:
    return Path(round_dir) / FILE


def saved_counts(round_dir: Path) -> dict[str, int] | None:
    p = path(round_dir)
    return json.loads(p.read_text(encoding="utf-8")).get("counts") if p.exists() else None


def load(round_dir: Path) -> dict[str, list[Doc]]:
    """Per station key, the documents RIK's register lists; {} when the round's register wasn't read."""
    p = path(round_dir)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    labels = data.get("labels") or []
    return {key: [doc(labels[i], rel, uploaded) for i, rel, uploaded in rows]
            for key, rows in (data.get("stations") or {}).items()}


def save(round_dir: Path, data: dict) -> bool:
    """Write documents.json; False when the content is what the file already holds."""
    p = path(round_dir)
    text = jsonfile.dumps(data, "stations")
    if p.exists() and p.read_text(encoding="utf-8") == text:
        return False
    p.write_text(text, encoding="utf-8")
    return True


# --- a station's documents -----------------------------------------------------------------------


def order(docs) -> list[Doc]:
    """Documents by kind, then the original vote before a repeated one, then by upload time."""
    return sorted(docs, key=lambda d: (KINDS.index(d.kind), d.repeat, d.uploaded, d.url))


def for_station(links: list[tuple[str, str]], register: list[Doc] | None = None) -> list[Doc]:
    """A station's documents: those in the results file (label, url pairs) and those in the register, each once,
    by kind and then by upload time."""
    out: dict[str, Doc] = {}
    for label, url in links:
        d = doc(label, url)
        out.setdefault(path_of(d.url), d)
    for d in register or []:
        out.setdefault(path_of(d.url), d)
    return order(out.values())
