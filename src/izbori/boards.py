"""Controllers: which lists put a member on each polling station's board in its extended composition.

Source: RIK's register of decisions appointing polling boards (document type 4). Most decisions are scans,
so they are read with OCR. Only three things are kept per decision: the polling station, its address, and for
each list whether it appointed a member and a deputy. Names in the decisions are never stored or printed.

This shows who was appointed before election day, not who turned up; attendance is only in the minutes."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from izbori.translit import latin

# --- the register of decisions -----------------------------------------------------------------


@dataclass
class BoardDoc:
    id: str
    municipality: str
    station: str  # polling station number as RIK lists it
    title: str
    decision: str
    published: str
    url: str
    kind: str = ""
    repeat: bool = False


def classify(title: str, decision: str) -> tuple[str, bool]:
    """Kind of decision, from RIK's label and the commission's own title (commissions sometimes mislabel)."""
    text = f"{title} {decision}".upper()
    repeat = "ПОНОВН" in text or "PONOVN" in text
    extended = "ПРОШИРЕН" in text or "PROŠIREN" in text or "PROSIREN" in text
    if not extended:
        return ("standing" if ("СТАЛН" in text or "STALN" in text) else "other"), repeat
    if any(w in text for w in ("ОДБИЈ", "ОДБАЦ", "ODBIJ", "ODBAC")):
        return "extended_rejected", repeat
    if any(w in text for w in ("ПРЕСТАН", "РАЗРЕШ", "PRESTAN", "RAZREŠ")):
        return "extended_end", repeat
    if "ИЗМЕН" in text or "IZMEN" in text:
        return "extended_change", repeat
    return "extended", repeat  # appointment, including supplements (допуна)


def doc_id(url: str) -> str:
    m = re.search(r"additionalDocuments/(\d+)/(\d+)/", url)
    return f"{m.group(1)}{m.group(2)}" if m else url


def parse_index_records(records: list[dict]) -> list[BoardDoc]:
    docs = []
    for r in records:
        links = re.findall(r'href="([^"]+)"', " ".join(r.get("extfiles_link") or []))
        if not links:
            continue
        url = links[0]
        station = (r.get("election_station_title") or "").split("-", 1)[0].strip()
        kind, repeat = classify(r.get("document_name") or "", r.get("election_board_decision") or "")
        docs.append(BoardDoc(id=doc_id(url), municipality=(r.get("municipality_display_name") or "").strip(),
                             station=station, title=(r.get("document_name") or "").strip(),
                             decision=(r.get("election_board_decision") or "").strip(),
                             published=str(r.get("datetime") or ""), url=url, kind=kind, repeat=repeat))
    return docs


def index_query(page: int, round_id: str, rik_type: int) -> str:
    params = [("page", page), ("filters[document-type]", 4), ("filters[election-round]", round_id),
              ("filters[municipality-id]", 0), ("filters[election_station]", -1),
              ("filters[additional-data]", 0), ("order", 2), ("sort", 2), ("election_type", rik_type)]
    return "/get-additional-documents?" + urllib.parse.urlencode(params)


def last_page(pagination_html: str) -> int:
    pages = [int(p) for p in re.findall(r'data-page="(\d+)"', pagination_html or "")]
    return max(pages) if pages else 1


# --- reading a decision ------------------------------------------------------------------------

LETTERS = re.compile(r"[A-Za-zА-Яа-яЂђЈјЉљЊњЋћЏџČčĆćŠšŽžĐđ]")
SLOT = re.compile(r"(?:^|\n)[\s\-–—~+•]*(\d{1,2})\s*[.,]\s*(?:члан|clan|član)\b\s*:?", re.IGNORECASE)
STATION = re.compile(r"(?:БИРАЧКО\s+МЕСТО\s+БРОЈ|BIRAČKO\s+MESTO\s+BROJ|BIRACKO\s+MESTO\s+BROJ)\s*[:.]?\s*(\d+)", re.I)
END = re.compile(r"\n\s*(?:2\s*[.,]\s*Ово\s+решење|2\s*[.,]\s*Ovo\s+rešenje|Образложење|Obrazloženje)", re.I)
DEPUTY = re.compile(r"заменик[^:]{0,20}:|zamenik[^:]{0,20}:", re.I)
PROPOSER = re.compile(r"на\s+предлог|na\s+predlog", re.I)


@dataclass
class Slot:
    member: bool
    deputy: bool
    list_text: str


@dataclass
class Decision:
    station: str | None
    address: str
    slots: list[Slot] = field(default_factory=list)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for a, b in (("–", "-"), ("—", "-"), ("−", "-"), ("„", '"'), ("“", '"'), ("”", '"'),
                 (" ", " "), ("\r", "")):
        text = text.replace(a, b)
    return text


def _filled(part: str) -> bool:
    part = re.sub(r"\s+и\s*$|\s+i\s*$", "", part.strip())
    return len(LETTERS.findall(part)) >= 3


def parse_decision(text: str) -> Decision:
    text = _normalize(text)
    m = STATION.search(text)
    station = m.group(1) if m else None
    address = ""
    if m:
        rest = text[m.end():].split("\n")
        lines = [ln.strip() for ln in rest[1:4]]
        for ln in lines:
            if not ln:
                continue
            if ln.startswith("(") or re.match(r"^\d+\s*[.,]\s*(У|U)\s", ln):
                break
            address = ln.strip(" ,;")
            break
    body = text
    end = END.search(text)
    if end:
        body = text[:end.start()]
    starts = list(SLOT.finditer(body))
    slots = []
    for k, sm in enumerate(starts):
        chunk = body[sm.end(): starts[k + 1].start() if k + 1 < len(starts) else len(body)]
        chunk = " ".join(chunk.split())
        prop = PROPOSER.search(chunk)
        if not prop:
            continue
        head, tail = chunk[:prop.start()], chunk[prop.end():]
        dep = DEPUTY.search(head)
        member_part = head[:dep.start()] if dep else head
        deputy_part = head[dep.end():] if dep else ""
        member_part = member_part.rstrip(" ,;-")
        list_text = re.sub(r"^\s*(подносиоца|podnosioca|посланичке групе|poslaničke grupe|групе грађана|grupe građana)"
                           r"\s*", "", tail.strip(), flags=re.I)
        list_text = re.sub(r"^\s*(изборне листе|izborne liste)\s*", "", list_text, flags=re.I).strip(" ;.")
        slots.append(Slot(member=_filled(member_part), deputy=_filled(deputy_part), list_text=list_text))
    return Decision(station=station, address=address, slots=slots)


# --- matching a list's name to the ballot ----------------------------------------------------------

STOP = {"IZBORNA", "IZBORNE", "LISTA", "LISTE", "PREDLOG", "PODNOSIOCA", "POSLANICKE", "GRUPE", "GRADJANA", "DR",
        "PROF", "ZA", "THE", "SRBIJE", "SRBIJA", "STRANKA", "POKRET", "KOALICIJA"}


def tokens(name: str) -> set[str]:
    s = latin(name).upper().replace("Đ", "DJ")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    words = re.findall(r"[A-Z]{3,}", s)
    return {w for w in words if w not in STOP}


def match_list(text: str, contestants: list[dict]) -> int | None:
    """Ballot number of the contestant whose name best matches `text`, or None when unclear."""
    t = tokens(text)
    if not t:
        return None
    scored = []
    for number, c in enumerate(contestants, start=1):
        names = [c.get("name", ""), c.get("rik_name", ""), c.get("short", "")]
        ct = set().union(*(tokens(n) for n in names if n))
        if not ct:
            continue
        overlap = len(t & ct)
        scored.append((overlap / min(len(t), len(ct)), overlap, number))
    scored.sort(reverse=True)
    if not scored or scored[0][1] < 2 and scored[0][0] < 1:
        return None
    best = scored[0]
    if best[0] < 0.5:
        return None
    if len(scored) > 1 and scored[1][0] >= best[0] and scored[1][1] >= best[1]:
        return None
    return best[2]


# --- getting text out of a PDF -----------------------------------------------------------------


def pdf_text(pdf: bytes, max_pages: int = 3, lang: str = "srp+srp_latn", dpi: int = 200) -> str:
    """The decision's text: the PDF's own text layer when it has one, otherwise OCR of the first pages."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "doc.pdf"
        path.write_bytes(pdf)
        if shutil.which("pdftotext"):
            r = subprocess.run(["pdftotext", "-layout", "-l", str(max_pages), str(path), "-"], capture_output=True,
                               text=True)
            if r.returncode == 0 and len(LETTERS.findall(r.stdout)) > 200 and SLOT.search(r.stdout):
                return r.stdout
        out = []
        for page in range(1, max_pages + 1):
            prefix = Path(tmp) / f"p{page}"
            r = subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-f", str(page), "-l", str(page),
                                str(path), str(prefix)], capture_output=True)
            images = sorted(Path(tmp).glob(f"p{page}*.png"))
            if r.returncode != 0 or not images:
                break
            ocr = subprocess.run(["tesseract", str(images[0]), "-", "-l", lang], capture_output=True, text=True,
                                 env={**os.environ, "OMP_THREAD_LIMIT": "1"})
            out.append(ocr.stdout)
            images[0].unlink()
            if END.search("\n" + ocr.stdout):
                break
        return "\n".join(out)


# --- the per-round store -----------------------------------------------------------------------


def store_path(round_dir: Path) -> Path:
    return Path(round_dir) / "boards.json"


def load_store(round_dir: Path) -> dict:
    p = store_path(round_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"docs": {}}


def save_store(round_dir: Path, store: dict) -> None:
    store_path(round_dir).write_text(json.dumps(store, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                     encoding="utf-8")


KEEP_WORDS = {"члан", "члана", "заменик", "на", "предлог", "подносиоца", "изборне", "листе", "посланичке", "групе",
              "бирачко", "место", "број", "бм", "и", "решење", "проширеном", "саставу", "сталном", "clan", "član",
              "zamenik", "predlog", "podnosioca", "izborne", "liste", "biračko", "mesto", "broj", "rešenje"}


def shape(text: str, limit: int = 1500) -> str:
    """The layout of a decision with every word that isn't a known keyword masked, so no name is shown."""
    def mask(m: re.Match) -> str:
        w = m.group(0)
        return w if w.lower() in KEEP_WORDS else "x" * min(len(w), 3)
    return LETTERS_WORD.sub(mask, text)[:limit]


LETTERS_WORD = re.compile(r"[A-Za-zА-Яа-яЂђЈјЉљЊњЋћЏџČčĆćŠšŽžĐđ]+")


def read_doc(doc: BoardDoc, pdf: bytes, contestants: list[dict], station_key: str | None,
             diagnose: bool = False) -> dict:
    """What the store keeps about one decision: no names, only lists, yes/no and the address."""
    text = pdf_text(pdf)
    decision = parse_decision(text)
    slots = []
    unmatched = 0
    for s in decision.slots:
        number = match_list(s.list_text, contestants)
        if number is None:
            unmatched += 1
        slots.append([number, s.member, s.deputy])
    result = {"s": station_key, "k": doc.kind, "r": doc.repeat, "t": doc.published, "slots": slots,
              "unmatched": unmatched, "addr": decision.address, "unparsed": not slots,
              "station_ok": decision.station is None or decision.station == doc.station}
    if diagnose and not slots:
        result["_shape"] = shape(text)
    return result


def coverage(store: dict) -> dict[str, dict]:
    """Per station: for each ballot number, whether a member and a deputy were appointed.

    Appointments and supplements add up. If the station voted again and got new boards, only those count."""
    by_station: dict[str, list[dict]] = {}
    unread: dict[str, int] = {}
    for d in store.get("docs", {}).values():
        if not d.get("s") or d.get("k") != "extended" or d.get("slots") is None:
            continue
        if d.get("unparsed") or not d["slots"]:
            unread[d["s"]] = unread.get(d["s"], 0) + 1
            continue
        by_station.setdefault(d["s"], []).append(d)
    out = {}
    for key, docs in by_station.items():
        if any(d.get("r") for d in docs):
            docs = [d for d in docs if d.get("r")]
        lists: dict[str, dict] = {}
        for d in sorted(docs, key=lambda d: d.get("t") or ""):
            for number, member, deputy in d["slots"]:
                if number is None:
                    continue
                cur = lists.setdefault(str(number), {"member": False, "deputy": False})
                cur["member"] = cur["member"] or bool(member)
                cur["deputy"] = cur["deputy"] or bool(deputy)
        address = next((d["addr"] for d in reversed(docs) if d.get("addr")), "")
        unmatched = sum(d.get("unmatched", 0) for d in docs)
        out[key] = {"lists": lists, "address": address, "unmatched": unmatched, "docs": len(docs),
                    "unread": unread.get(key, 0)}
    for key, n in unread.items():
        out.setdefault(key, {"lists": None, "address": "", "unmatched": 0, "docs": 0, "unread": n})
    return out


def municipality_key(name: str) -> str:
    s = latin(name).upper()
    s = re.sub(r"^(GRADSKA OPŠTINA|GRADSKA OPSTINA|GRAD|OPŠTINA|OPSTINA)\s+", "", s.strip())
    s = unicodedata.normalize("NFD", s.replace("Đ", "DJ"))
    return "".join(ch for ch in s if ch.isalnum() and not unicodedata.combining(ch))


# --- running it --------------------------------------------------------------------------------


def _work(args: tuple) -> tuple[str, dict | None, str | None]:
    """Download and read one decision. Runs in a worker process; returns no names."""
    from izbori.rik import Client
    doc, contestants, station_key, base, diagnose = args
    try:
        pdf = Client(base=base).get_bytes(doc["url"])
        return doc["id"], read_doc(BoardDoc(**doc), pdf, contestants, station_key, diagnose), None
    except Exception as e:  # noqa: BLE001 - one bad document must not stop the rest
        return doc["id"], None, type(e).__name__


def fetch_index(client, round_id: str, rik_type: int, known: frozenset = frozenset(), log=print,
                threads: int = 4) -> list[BoardDoc]:
    """All decisions on polling boards for the round, newest first.

    RIK lists them newest first, so once decisions are known, paging stops at the first page with nothing new."""
    from concurrent.futures import ThreadPoolExecutor

    def page_docs(page: int) -> list[BoardDoc]:
        return parse_index_records((client.get_json(index_query(page, round_id, rik_type)) or {}).get("records") or [])

    first = client.get_json(index_query(1, round_id, rik_type)) or {}
    pages = last_page(first.get("pagination", ""))
    docs = parse_index_records(first.get("records") or [])
    if known:
        page = 1
        while page < pages and not all(d.id in known for d in docs[-10:]):
            page += 1
            docs.extend(page_docs(page))
    else:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            for k, batch in enumerate(ex.map(page_docs, range(2, pages + 1)), start=2):
                docs.extend(batch)
                if k % 500 == 0:
                    log(f"index: page {k}/{pages}")
    seen, unique = set(), []
    for d in docs:
        if d.id not in seen:
            seen.add(d.id)
            unique.append(d)
    return unique


def run(round_dir: Path, round_id: str, rik_type: int, contestants: list[dict], stations: dict[str, str], client,
        workers: int = 4, budget_seconds: float = 5 * 3600, limit: int | None = None, log=print,
        save_every: int = 200, checkpoint=None, diagnose: int = 0, retry_unparsed: bool = False) -> dict:
    """Index the round's board decisions and read the ones not yet read.

    `stations` maps a municipality key (see municipality_key) to its code in the results file."""
    import time
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

    started = time.monotonic()
    store = load_store(round_dir)
    known = store.setdefault("docs", {})
    # Page through the whole register unless the last run read everything; otherwise older unread decisions
    # deep in the register would be missed.
    docs = fetch_index(client, round_id, rik_type, frozenset(known) if store.get("complete") else frozenset(), log)
    store["indexed"] = len(set(known) | {d.id for d in docs})
    todo = []
    for d in docs:
        code = stations.get(municipality_key(d.municipality))
        key = f"{code}/{d.station}" if code and d.station else None
        if d.kind != "extended":
            if d.id not in known:
                known[d.id] = {"s": key, "k": d.kind, "r": d.repeat, "t": d.published}
            continue
        if d.id in known and known[d.id].get("slots") is not None and not (
                retry_unparsed and known[d.id].get("unparsed")):
            continue
        todo.append((d.__dict__, contestants, key, client.base, diagnose > 0))
    if limit is not None:
        todo = todo[:limit]
    log(f"{len(docs)} decisions indexed, {len(todo)} to read")
    done = failed = unparsed = shown = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = set()
        queue = iter(todo)
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
                did, result, error = f.result()
                if result is not None:
                    layout = result.pop("_shape", None)
                    if result.get("unparsed"):
                        unparsed += 1
                        if layout and shown < diagnose:
                            shown += 1
                            log(f"unreadable decision {did} ({result.get('s')}), layout with names masked:\n{layout}")
                    known[did] = result
                    done += 1
                else:
                    failed += 1
                    log(f"could not read decision {did}: {error}")
                if (done + failed) % save_every == 0:
                    save_store(round_dir, store)
                    log(f"read {done}, failed {failed}")
                    if checkpoint:
                        checkpoint()
    store["complete"] = limit is None and done + failed == len(todo) and failed == 0
    save_store(round_dir, store)
    log(f"read {done} (unreadable {unparsed}), failed {failed}, left {len(todo) - done - failed}")
    return {"indexed": len(docs), "read": done, "failed": failed, "unparsed": unparsed,
            "left": len(todo) - done - failed}
