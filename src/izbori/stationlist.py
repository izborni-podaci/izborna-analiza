"""The local commissions' decisions on polling stations, read for each station's settlement.

The law (Закон о избору народних посланика, art. 56–57) has the local electoral commission determine the polling
stations by an act that gives, for each, its number, name, address and the area it covers (streets, a village, a
settlement), published on the web. RIK's own results carry neither the address nor the area, so these acts are the
primary source for which census settlement a station is in. `data/station_lists.csv` lists the acts the maintainer
found (round, municipality code, link, note); `izbori stationlist` downloads each, reads it (a PDF's text layer,
OCR for a scan, the XML of a .docx), cuts it into one row per station number and finds in each row a settlement of
the municipality. The result, `data/rounds/<id>/station_lists.json`, holds only station keys, settlements and the
link; the decisions name no people, and nothing else of them is kept. An act of an earlier election is read for
that election; the same place at a later election takes the settlement from it (settlements.inherit).
"""
from __future__ import annotations

import csv
import json
import re
import zipfile
from io import BytesIO
from pathlib import Path

from izbori import jsonfile
from izbori.settlements import names, norm

LISTS_FILE = "station_lists.csv"
STORE = "station_lists.json"
ROW_NUMBER = r"(?:^|\n)[\s|.]*{n}\s*[.|)]?(?=[\s|])"  # the station's number at the start of a line (or table cell)


def load_lists(path: Path, log=None) -> list[dict]:
    """The acts to read: round, municipality_code, url, note."""
    out = []
    if not Path(path).exists():
        return out
    with open(path, encoding="utf-8", newline="") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            row = {k: (v or "").strip() for k, v in row.items() if k}
            if not all(row.get(k) for k in ("round", "municipality_code", "url")):
                if log:
                    log(f"{path}:{n}: needs a round, a municipality code and a link")
                continue
            out.append(row)
    return out


def docx_text(data: bytes) -> str:
    """The text of a .docx: paragraphs and table rows on their own lines, cells apart."""
    with zipfile.ZipFile(BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"</w:tc>", " | ", xml)
    xml = re.sub(r"</w:tr>", "\n", xml)
    xml = re.sub(r"<w:tab/>", " ", xml)
    return re.sub(r"<[^>]+>", "", xml)


def document_text(data: bytes, url: str) -> str:
    """The act's text: a .docx by its XML, a PDF by its text layer, or OCR of a scan (boards.pdf_text), page by page
    up to 40 pages — an act lists up to a few hundred stations."""
    if url.lower().endswith(".docx") or data[:2] == b"PK":
        return docx_text(data)
    from izbori import boards
    text = boards.pdf_text(data, max_pages=40)
    if len(re.findall(r"[А-Яа-яA-Za-z]", text)) < 200:
        text = boards.pdf_text(data, max_pages=40, ocr=True, psm=6)
    return text


def rows(text: str, count: int) -> dict[int, str]:
    """The act cut into the rows of its stations: number → the text from that number to the next. Numbers are
    looked for in order, each after the last found, so a number inside a row (a house number, a year) is passed
    over; a number OCR lost is skipped."""
    text = text.replace("\r", "")
    out: dict[int, str] = {}
    pos = 0
    starts: list[tuple[int, int, int]] = []  # (number, start of text, end of match)
    n = 1
    while n <= count:
        m = re.compile(ROW_NUMBER.format(n=n)).search(text, pos)
        if m:
            starts.append((n, m.start(), m.end()))
            pos = m.end()
        n += 1
    for k, (n, start, end) in enumerate(starts):
        stop = starts[k + 1][1] if k + 1 < len(starts) else len(text)
        out[n] = text[end:stop]
    return out


def settlement_in(row: str, known: list[tuple[str, str, object]]) -> str | None:
    """The census settlement a row names: the first one found (longest names first) whose whole words stand in the
    row; None when none or several different ones."""
    found: dict[str, int] = {}  # printed name → where its (compared) name first stands in the row
    r = f" {norm(row)} "
    for n, printed, _ in known:
        at = r.find(f" {n} ")
        if at >= 0 and printed not in found:
            found[printed] = at
    if not found:
        return None
    return min(found, key=found.get)  # one name, or the first in the row (the area column comes last)


def read_act(text: str, stations: list, units: list) -> dict[str, dict]:
    """Per station key, the settlement its row of the act names. The act's row for a station must also share a
    word with the station's name in the results (or that name is a bare kind of building), so a renumbering
    between the act and the vote doesn't put a station in another station's settlement."""
    from izbori.places import words
    known = names(units)
    by_number = {int(s.number): s for s in stations if s.number.isdigit()}
    out: dict[str, dict] = {}
    if not by_number:
        return out
    for n, row in rows(text, max(by_number)).items():
        s = by_number.get(n)
        if s is None:
            continue
        settlement = settlement_in(row, known)
        if not settlement:
            continue
        own = words(s.name)
        row_words = set(norm(row).split())
        if own and not (own & row_words) and not any(w in row_words for w in {x[:5] for x in own if len(x) > 5}):
            out[s.key] = {"s": settlement, "ok": False}  # the act's row doesn't look like this station
            continue
        out[s.key] = {"s": settlement, "ok": True}
    return out


def load_store(round_dir: Path) -> dict:
    p = Path(round_dir) / STORE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"docs": {}, "stations": {}}


def save_store(round_dir: Path, store: dict) -> None:
    (Path(round_dir) / STORE).write_text(jsonfile.dumps(store, "stations"), encoding="utf-8")


def listed(round_dir: Path) -> dict[str, str]:
    """Station key → settlement from the acts read, the rows that matched the station's name only."""
    return {k: v["s"] for k, v in load_store(round_dir).get("stations", {}).items() if v.get("ok")}
