"""Observers' records (form RG-11): who observed a polling board, and whether they wrote remarks.

Two parts work together:

1. A person reads the record and writes down, in data/rounds/<id>/observer_reviews.csv, whether observers wrote
   remarks, with a short neutral summary that names no one. A confirmed remark is a flag; a record read and found
   empty is shown as read.
2. To know which records to read first, each one is read once with OCR and scored by how much is written in its
   remark lines. Nothing of the text is kept, only numbers, in data/rounds/<id>/observers.json; the score orders
   the list to review (`izbori observers --review`) and is never a flag.

For each observer the form has a printed line "ПРИМЕДБЕ на поступак спровођења гласања на бирачком месту су
следеће:", lines to write on, and "(примедбе уписује представник посматрача ...)" below them. The score is the
share of dark pixels between those two lines, leaving out the printed rules, plus the words OCR finds there.
Writing "нема" or striking out the empty lines also leaves ink, so a high score means "read this first", not
"there are remarks"."""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from izbori.documents import path_of

REVIEWS = "observer_reviews.csv"
SCORES = "observers.json"
FIELDS = ["municipality_code", "station", "remarks", "summary_sr", "summary_en", "checked"]
YES = {"да", "da", "yes", "y", "1", "true"}
NO = {"не", "ne", "no", "n", "0", "false"}


# --- reviews by a person -------------------------------------------------------------------------


@dataclass(frozen=True)
class Review:
    remarks: bool
    summary_sr: str = ""
    summary_en: str = ""
    checked: str = ""

    def summary(self, loc: str) -> str:
        from izbori.translit import latin
        return (self.summary_en or latin(self.summary_sr)) if loc == "en" else self.summary_sr


def load_reviews(round_dir: Path) -> dict[str, Review]:
    """Station key → what a person found in its observers' record. Rows without a clear yes or no are skipped."""
    p = Path(round_dir) / REVIEWS
    if not p.exists():
        return {}
    out = {}
    with p.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            row = {k: (v or "").strip() for k, v in row.items() if k}
            answer = row.get("remarks", "").lower()
            if not row.get("municipality_code") or not row.get("station") or answer not in YES | NO:
                continue
            out[f"{row['municipality_code']}/{row['station']}"] = Review(
                answer in YES, row.get("summary_sr", ""), row.get("summary_en", ""), row.get("checked", ""))
    return out


def write_template(round_dir: Path) -> Path:
    p = Path(round_dir) / REVIEWS
    if not p.exists():
        with p.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(FIELDS)
    return p


# --- the OCR score -------------------------------------------------------------------------------

START = re.compile(r"следе|slede[ćc]", re.I)  # "су следеће:" (OCR often misreads the ћ)
START_WORD = re.compile(r"^(следе|slede)\S{0,2}[еe][:;.,]?$", re.I)  # "следеће:", not the header's "следећи"
TOPIC = re.compile(r"примедб|primedb", re.I)  # … on the line that begins "ПРИМЕДБЕ на поступак", not the header's
#                                               "присутни су следећи представници"
RULE_RUN = 30  # a dark run this long along a row is a printed rule, even on a crooked scan; pen strokes are shorter
END = re.compile(r"упису|upisu", re.I)  # "(примедбе уписује …" (the ј is often misread too)
WORD = re.compile(r"[A-Za-zА-Яа-яЂђЈјЉљЊњЋћЏџČčĆćŠšŽžĐđ]{2,}")
NONE = re.compile(r"^(нема|nema|без|bez|нема\.|nema\.)$", re.I)
DARK = bytes(1 if v < 170 else 0 for v in range(256))  # a scan of blue pen is often only mid-grey


@dataclass
class Word:
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int
    line: tuple

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


def read_pgm(path: Path) -> tuple[int, int, bytes]:
    data = Path(path).read_bytes()
    fields, i = [], 0
    while len(fields) < 4:
        while data[i:i + 1].isspace():
            i += 1
        if data[i:i + 1] == b"#":
            i = data.index(b"\n", i) + 1
            continue
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        fields.append(data[i:j])
        i = j
    if fields[0] != b"P5":
        raise ValueError("not a binary graymap")
    w, h = int(fields[1]), int(fields[2])
    return w, h, data[i + 1:i + 1 + w * h]


def parse_tsv(text: str) -> list[Word]:
    words = []
    for line in text.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) < 12 or cols[0] != "5" or not cols[11].strip():
            continue
        words.append(Word(cols[11].strip(), float(cols[10]), int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9]),
                          (cols[1], cols[2], cols[3], cols[4])))
    return words


def ink(img: bytes, w: int, x0: int, x1: int, y0: int, y1: int) -> tuple[float, int]:
    """Share of dark pixels in a box that belong to short strokes, leaving out the long runs of printed rules
    (which on a crooked scan run across several rows in pieces); and how many rows hold some such ink."""
    width = max(1, x1 - x0)
    counts = []
    for y in range(y0, y1):
        runs = img[y * w + x0:y * w + x1].translate(DARK).split(b"\x00")
        counts.append(sum(len(r) for r in runs if len(r) < RULE_RUN))
    if not counts:
        return 0.0, 0
    return sum(counts) / (len(counts) * width), sum(1 for n in counts if n > 0.01 * width)


PRINTED = ("представ", "посматра", "имао", "поступ", "спровођ", "спровоб", "гласањ", "гласан", "бирачк", "месту",
           "часова", "дошао", "напусти", "испред", "организ", "уписуј", "predstav", "posmatra", "postup", "glasanj",
           "biračk", "birack", "časova", "casova", "ispred")  # words of the printed form, not of a remark


def blocks(words: list[Word], w: int, h: int) -> list[tuple[int, int, int, int, list[Word]]]:
    """The remark areas: from each "… су следеће:" line down to the "(примедбе уписује …)" line below it.

    Each "(примедбе уписује" line closes the area of the nearest "следеће:" line above it, so the header's
    "следећи представници" (which OCR may read as "следеће") opens no area of its own; and an area starts below any
    printed words of the form that fall in it (the observer's name, times, organisation)."""
    lines: dict[tuple, list[Word]] = {}
    for word in words:
        lines.setdefault(word.line, []).append(word)
    starts: dict[tuple, list[Word]] = {}
    for x in words:
        if not START.search(x.text):
            continue
        # the word reads "следеће:", or "ПРИМЕДБЕ" opens its printed line (which OCR may cut in two when crooked)
        topic = [y for y in words if TOPIC.search(y.text) and y.left < x.left and abs(y.top - x.top) < 2 * x.height]
        if START_WORD.match(x.text) or topic:
            starts[x.line] = list({id(z): z for z in lines[x.line] + (lines[topic[0].line] if topic else [])}.values())
    ends = {x.line: lines[x.line] for x in words if END.search(x.text)}
    closing: dict[tuple, tuple[int, list[Word]]] = {}  # start line → (top of its end line, end line)
    for end in ends.values():
        e_top, e_left, e_right = min(x.top for x in end), min(x.left for x in end), max(x.right for x in end)
        above = [(k, st) for k, st in starts.items() if max(x.bottom for x in st) < e_top
                 and e_top - max(x.bottom for x in st) < 0.3 * h
                 and min(x.left for x in st) < e_right and max(x.right for x in st) > e_left]
        if not above:
            continue
        k, st = max(above, key=lambda item: max(x.bottom for x in item[1]))  # the nearest one above
        if k not in closing or e_top < closing[k][0]:
            closing[k] = (e_top, end)
    found = []
    for k, (e_top, end) in closing.items():
        start = starts[k]
        s_left, s_right = min(x.left for x in start), max(x.right for x in start)
        x0 = max(0, min(s_left, min(x.left for x in end)) - int(0.01 * w))
        x1 = min(w, max(s_right, max(x.right for x in end)))
        y0, y1 = max(x.bottom for x in start) + 4, e_top - 4
        printed = [x for x in words if x0 <= x.left + x.width / 2 <= x1 and y0 <= x.top + x.height / 2 <= y1
                   and x.conf >= 70 and x.text.lower().strip("(),.:;").startswith(PRINTED)]
        if printed:
            y0 = max(x.bottom for x in printed) + 4
        if y1 - y0 >= 10:
            found.append([x0, x1, y0, y1])
    if found:  # when OCR missed an end line, the area would run into the next observer's: cut it to the usual height
        usual = sorted(b[3] - b[2] for b in found)[len(found) // 2]
        for b in found:
            b[3] = min(b[3], b[2] + int(1.4 * usual))
    return [(x0, x1, y0, y1, [x for x in words if x0 <= x.left + x.width / 2 <= x1 and y0 <= x.top + x.height / 2 <= y1])
            for x0, x1, y0, y1 in sorted(found, key=lambda b: (b[0] > w // 2, b[2]))]


def score_pages(pages: list[tuple[int, int, bytes, list[Word]]]) -> dict:
    """What is kept for one record: numbers only."""
    found = []
    for w, h, img, words in pages:
        for x0, x1, y0, y1, inside in blocks(words, w, h):
            density, rows = ink(img, w, x0, x1, y0, y1)
            written = [x for x in inside if x.conf >= 30 and WORD.search(x.text)]
            none = any(NONE.match(x.text.strip(".,:;")) for x in written)
            found.append({"ink": round(100 * density, 2), "rows": rows, "words": len(written), "none": none})
    if not found:
        return {"ok": False, "pages": len(pages), "blocks": 0, "score": None}
    best = max(b["ink"] + 0.5 * b["words"] - (2 if b["none"] and b["words"] <= 2 else 0) for b in found)
    return {"ok": True, "pages": len(pages), "blocks": len(found), "score": round(best, 2),
            "detail": [[b["ink"], b["rows"], b["words"], int(b["none"])] for b in found]}


def read_pdf(pdf: bytes, max_pages: int = 4, dpi: int = 200, lang: str = "srp+srp_latn") -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "doc.pdf"
        path.write_bytes(pdf)
        pages = []
        for page in range(1, max_pages + 1):
            prefix = Path(tmp) / f"p{page}"
            r = subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-f", str(page), "-l", str(page), str(path),
                                str(prefix)], capture_output=True)
            images = sorted(Path(tmp).glob(f"p{page}*.pgm"))
            if r.returncode != 0 or not images:
                break
            w, h, img = read_pgm(images[0])
            ocr = subprocess.run(["tesseract", str(images[0]), "-", "-l", lang, "tsv"], capture_output=True,
                                 text=True, env={**os.environ, "OMP_THREAD_LIMIT": "1"})
            pages.append((w, h, img, parse_tsv(ocr.stdout)))
            images[0].unlink()
        return score_pages(pages)


# --- the per-round store and the run -------------------------------------------------------------


def load_scores(round_dir: Path) -> dict:
    p = Path(round_dir) / SCORES
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"docs": {}}


def save_scores(round_dir: Path, store: dict) -> None:
    (Path(round_dir) / SCORES).write_text(json.dumps(store, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
                                          encoding="utf-8")


def _work(args: tuple) -> tuple[str, dict | None, str | None]:
    from izbori.rik import Client
    key, url, base = args
    try:
        return path_of(url), {"s": key, **read_pdf(Client(base=base).get_bytes(url))}, None
    except Exception as e:  # noqa: BLE001 - one bad document must not stop the rest
        return path_of(url), None, type(e).__name__


def run(round_dir: Path, records: list[tuple[str, str]], client, workers: int = 4, budget_seconds: float = 5 * 3600,
        limit: int | None = None, log=print, diagnose: int = 0, save_every: int = 100) -> dict:
    """Score the observers' records not scored yet. records: (station key, document url)."""
    import time
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

    started = time.monotonic()
    store = load_scores(round_dir)
    known = store.setdefault("docs", {})
    todo = [(key, url, client.base) for key, url in records if path_of(url) not in known]
    if limit is not None:
        todo = todo[:limit]
    log(f"{len(records)} observers' records, {len(todo)} to read")
    done = failed = shown = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending, queue = set(), iter(todo)
        while True:
            while len(pending) < workers * 2 and time.monotonic() - started < budget_seconds:
                item = next(queue, None)
                if item is None:
                    break
                pending.add(pool.submit(_work, item))
            if not pending:
                break
            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
            for f in finished:
                doc, result, error = f.result()
                if result is None:
                    failed += 1
                    log(f"could not read {doc}: {error}")
                    continue
                known[doc] = result
                done += 1
                if shown < diagnose:
                    shown += 1
                    log(f"{result['s']}: pages {result['pages']}, remark areas {result['blocks']}, score "
                        f"{result['score']}, per area [ink %, rows with ink, words, 'нема'] {result.get('detail')}")
                if (done + failed) % save_every == 0:
                    save_scores(round_dir, store)
                    log(f"read {done}, failed {failed}")
    save_scores(round_dir, store)
    scored = [d["score"] for d in known.values() if d.get("score") is not None]
    log(f"read {done}, failed {failed}, left {len(todo) - done - failed}; scored {len(scored)} of {len(known)}")
    return {"read": done, "failed": failed, "left": len(todo) - done - failed}


def review_rows(analysis, scores: dict) -> list[dict]:
    """Observers' records not yet reviewed, those with most written in their remark lines first; records OCR
    couldn't place at the end."""
    reviewed = analysis.reviews
    rows = []
    for s in analysis.round.stations:
        if s.key in reviewed:
            continue
        docs = [d for d in analysis.documents.get(s.key, []) if d.kind == "observers"]
        if not docs:
            continue
        found = [scores.get(path_of(d.url)) or {} for d in docs]
        values = [x["score"] for x in found if x.get("score") is not None]
        rows.append({"s": s, "docs": docs, "score": max(values) if values else None,
                     "blocks": sum(x.get("blocks") or 0 for x in found),
                     "flags": [f for f in analysis.by_station.get(s.key, []) if f.check.group == "records"]})
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0), r["s"].municipality_code,
                             int(r["s"].number) if r["s"].number.isdigit() else 0))
    return rows


def write_review(rows: list[dict], rid: str, csv_path: Path, html_path: Path | None = None) -> None:
    """The list to review, with the columns of observer_reviews.csv left empty to fill in."""
    import html

    from izbori.i18n import check_name
    from izbori.links import safe_url
    from izbori.translit import latin
    with Path(csv_path).open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["score", "municipality", "station_name", "observers_record", "other", *FIELDS])
        for r in rows:
            s = r["s"]
            w.writerow(["" if r["score"] is None else f"{r['score']:.1f}", latin(s.municipality), latin(s.name),
                        " ".join(safe_url(d.url) for d in r["docs"]),
                        "; ".join(latin(check_name(f.code, "lat")) for f in r["flags"]),
                        s.municipality_code, s.number, "", "", "", ""])
    if html_path:
        parts = [f"<!doctype html><meta charset='utf-8'><title>Zapisnici o posmatračima za čitanje · {rid}</title>",
                 "<style>body{font:14px/1.45 system-ui,sans-serif;margin:24px;max-width:960px}table{border-collapse:"
                 "collapse;width:100%}td,th{text-align:left;padding:4px 6px;border-bottom:1px solid #eee}"
                 ".n{font-variant-numeric:tabular-nums;white-space:nowrap}</style>",
                 f"<h1>Zapisnici o posmatračima za čitanje ({len(rows)})</h1>",
                 "<p>Redosled daje automatsko čitanje: koliko je upisano u linije za primedbe. Visok skor znači "
                 "„pročitaj prvo”, ne „ima primedbi”: i „nema” ili precrtan prostor ostavljaju trag. Šta si našao "
                 "upiši u observer_reviews.csv (da/ne, kratak opis bez imena).</p>",
                 "<table><tr><th>Skor</th><th>Opština</th><th>BM</th><th>Mesto</th><th>Zapisnik</th><th>Drugo</th></tr>"]
        for r in rows:
            s = r["s"]
            links = " ".join(f"<a href='{html.escape(safe_url(d.url))}'>RG-11{' (ponovno)' if d.repeat else ''}</a>"
                             for d in r["docs"])
            score = "—" if r["score"] is None else f"{r['score']:.1f}"
            parts.append(f"<tr><td class='n'>{score}</td><td>{html.escape(latin(s.municipality))}</td>"
                         f"<td class='n'>{html.escape(s.number)}</td><td>{html.escape(latin(s.name))}</td>"
                         f"<td>{links}</td><td>{html.escape('; '.join(latin(check_name(f.code, 'lat')) for f in r['flags']))}"
                         f"</td></tr>")
        parts.append("</table>")
        Path(html_path).write_text("".join(parts), encoding="utf-8")
