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

from izbori import jsonfile
from izbori.config import RIK_PUBLIC
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
    station_name: str = ""  # the station's name in the register's title; only to place the decision, never kept


def classify(title: str, decision: str) -> tuple[str, bool]:
    """Kind of decision, from RIK's label and the commission's own title (commissions sometimes mislabel)."""
    text = f"{title} {decision}".upper()
    repeat = "ПОНОВН" in text or "PONOVN" in text
    extended = "ПРОШИРЕН" in text or "PROŠIREN" in text or "PROSIREN" in text
    if not extended:
        if "СТАЛН" not in text and "STALN" not in text:
            return "other", repeat
        changed = any(w in text for w in ("ИЗМЕН", "IZMEN", "РАЗРЕШ", "RAZREŠ", "ПРЕСТАН", "PRESTAN"))
        return ("standing_change" if changed else "standing"), repeat
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


def link_path(url: str) -> str:
    """The decision's path on RIK's site, decoded (kept so the station's page can link to it)."""
    return urllib.parse.unquote(urllib.parse.urlsplit(url.strip()).path)


# Kinds of decision as listed among a station's documents (documents.KINDS), in that order.
DOC_KINDS = {"standing": "board_standing", "standing_change": "board_standing_change", "extended": "board_extended",
             "extended_change": "board_extended_change", "extended_end": "board_extended_change",
             "extended_rejected": "board_refused", "other": "board_other"}


def station_docs(store: dict) -> dict:
    """Per station key, its decisions on the polling board as documents to link (documents.Doc), oldest first.

    Only decisions whose link was kept; the label is left empty, as the kind says what each one is."""
    from datetime import datetime

    from izbori.documents import Doc, order
    from izbori.i18n import BELGRADE
    out: dict[str, list] = {}
    for d in store.get("docs", {}).values():
        if not d.get("s") or not d.get("u"):
            continue
        when = d.get("t") or ""
        if when.isdigit():
            when = datetime.fromtimestamp(int(when), tz=BELGRADE).strftime("%Y-%m-%dT%H:%M")
        url = d["u"] if d["u"].startswith("http") else RIK_PUBLIC.rstrip("/") + d["u"]
        out.setdefault(d["s"], []).append(Doc(DOC_KINDS.get(d.get("k"), "board_other"), bool(d.get("r")), "", url,
                                              when))
    return {key: order(docs) for key, docs in out.items()}


def parse_index_records(records: list[dict]) -> list[BoardDoc]:
    docs = []
    for r in records:
        links = re.findall(r'href="([^"]+)"', " ".join(r.get("extfiles_link") or []))
        if not links:
            continue
        url = links[0]
        number, _, name = (r.get("election_station_title") or "").partition("-")
        kind, repeat = classify(r.get("document_name") or "", r.get("election_board_decision") or "")
        docs.append(BoardDoc(id=doc_id(url), municipality=(r.get("municipality_display_name") or "").strip(),
                             station=number.strip(), title=(r.get("document_name") or "").strip(),
                             decision=(r.get("election_board_decision") or "").strip(),
                             published=str(r.get("datetime") or ""), url=url, kind=kind, repeat=repeat,
                             station_name=name.strip()))
    return docs


def index_query(page: int, round_id: str, rik_type: int, document_type: int = 4) -> str:
    """A page of RIK's register of additional documents: type 4 are the decisions on polling boards, type 1 the
    documents of the municipalities' electoral commissions."""
    params = [("page", page), ("filters[document-type]", document_type), ("filters[election-round]", round_id),
              ("filters[municipality-id]", 0), ("filters[election_station]", -1),
              ("filters[additional-data]", 0), ("order", 2), ("sort", 2), ("election_type", rik_type)]
    return "/get-additional-documents?" + urllib.parse.urlencode(params)


def last_page(pagination_html: str) -> int:
    pages = [int(p) for p in re.findall(r'data-page="(\d+)"', pagination_html or "")]
    return max(pages) if pages else 1


# --- reading a decision ------------------------------------------------------------------------

LETTERS = re.compile(r"[A-Za-zА-Яа-яЂђЈјЉљЊњЋћЏџČčĆćŠšŽžĐđ]")
SLOT = re.compile(r"(?:^|\n)[\s\-–—~+•]*(\d{1,2})\s*[.,)]\s*(?:члан|clan|član)\b\s*:?", re.IGNORECASE)  # 1. or 1)
# Every member's or deputy's role, and every proposal, wherever they stand: for the layouts that don't number
# each member ("- члан: …", or each list first and its people under it). "члана" alone (genitive, as in "на основу
# члана 32") is never a role.
ROLE = re.compile(r"\b(заменик\s+члана|zamenik\s+[čc]lana|члан|[čc]lan)\b\s*[:;,.]?", re.IGNORECASE)

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


# Words of a member's line ("1. члан: <name>, на предлог подносиоца …"), never of an address. When OCR or a
# decision's layout puts such a line where the address should be, it carries a name and must not be kept.
PERSONAL = re.compile(r"члан|clan|član|заменик|zamenik|предлог|predlog|подносиоц|podnosioc|председни|predsedni|"
                      r"секретар|sekretar|именуј|imenuj", re.I)


def clean_address(text: str) -> str:
    """The address as read, or "" when what was read isn't one (a member's line, with a name)."""
    text = (text or "").strip(" ,;")
    return "" if not text or PERSONAL.search(text) else text


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
            address = clean_address(ln)
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
    return Decision(station=station, address=address, slots=slots or _unnumbered(body))


def _list_text(text: str) -> str:
    text = " ".join(text.split())
    text = re.sub(r"^\s*(подносиоца|podnosioca|посланичке групе|poslaničke grupe|групе грађана|grupe građana)\s*", "",
                  text, flags=re.I)
    return re.sub(r"^\s*(изборне листе|izborne liste)\s*", "", text, flags=re.I).strip(" ;.:")


def _unnumbered(body: str) -> list[Slot]:
    """Slots from a decision that doesn't number its members. Two layouts:
    - people first: "члан: <name> и заменик члана: <name>, на предлог подносиоца изборне листе <list>;", or each
      role on its own line with its own list ("- члан: <name> на предлог …"; "- заменик члана: <name>, на предлог …");
    - each list first: "На предлог подносиоца изборне листе <list>: члан: <name>, заменик члана: <name>".
    Which one it is follows from what comes first, a role or a proposal. Only filled-in or empty is kept."""
    places = list(STATION.finditer(body))
    if places:  # the members follow the last mention of the station; a proposal in the preamble isn't one of them
        body = body[places[-1].end():]
    events = sorted([(m.start(), m.end(), "deputy" if m.group(1).lower().startswith(("заменик", "zamenik")) else "member")
                     for m in ROLE.finditer(body)] + [(m.start(), m.end(), "list") for m in PROPOSER.finditer(body)])
    if not any(e[2] == "list" for e in events) or not any(e[2] != "list" for e in events):
        return []
    people_first = events[0][2] != "list"
    groups: list[tuple[str, list]] = []  # (list text, [(role, filled)])
    pending: list = []
    for k, (start, end, what) in enumerate(events):
        text = body[end: events[k + 1][0] if k + 1 < len(events) else len(body)]
        if what == "list":
            if people_first:
                groups.append((_list_text(text), pending))
                pending = []
            else:
                groups.append((_list_text(text), []))
        elif people_first:
            pending.append((what, _filled(text)))
        elif groups:
            groups[-1][1].append((what, _filled(text)))
    return [Slot(member=any(f for r, f in roles if r == "member"), deputy=any(f for r, f in roles if r == "deputy"),
                 list_text=lst) for lst, roles in groups if roles]


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


def scrub(store: dict) -> int:
    """Empty every kept address that isn't one (a member's line, with a name); how many were emptied."""
    n = 0
    for d in store.get("docs", {}).values():
        if d.get("addr") and not clean_address(d["addr"]):
            d["addr"] = ""
            n += 1
    return n


def load_store(round_dir: Path) -> dict:
    p = store_path(round_dir)
    store = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"docs": {}}
    scrub(store)  # a store written before addresses were checked never shows a name
    return store


def save_store(round_dir: Path, store: dict) -> None:
    scrub(store)
    store_path(round_dir).write_text(jsonfile.dumps(store, "docs"), encoding="utf-8")


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
    result = {"s": station_key, "k": doc.kind, "r": doc.repeat, "t": doc.published, "u": link_path(doc.url),
              "slots": slots, "unmatched": unmatched, "addr": decision.address, "unparsed": not slots,
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


def addresses(store: dict) -> dict[str, str]:
    """Per station: the address on its newest decision of any kind, where one was read."""
    out: dict[str, tuple[str, str]] = {}
    for d in store.get("docs", {}).values():
        if d.get("s") and d.get("addr"):
            when = d.get("t") or ""
            if d["s"] not in out or when >= out[d["s"]][0]:
                out[d["s"]] = (when, d["addr"])
    return {key: addr for key, (_, addr) in out.items()}


def municipality_key(name: str) -> str:
    s = latin(name).upper()
    s = re.sub(r"^(GRADSKA OPŠTINA|GRADSKA OPSTINA|GRAD|OPŠTINA|OPSTINA)\s+", "", s.strip())
    s = unicodedata.normalize("NFD", s.replace("Đ", "DJ"))
    return "".join(ch for ch in s if ch.isalnum() and not unicodedata.combining(ch))


def name_words(text: str) -> frozenset:
    s = latin(text or "").upper().replace("Đ", "DJ")
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch))
    return frozenset(re.findall(r"[A-Z0-9]+", s))


def same_station(a: str, b: str) -> bool:
    """Two names of one polling station: the same words, give or take a quarter (quotes, abbreviations)."""
    wa, wb = name_words(a), name_words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.75


class Placer:
    """Which polling station a decision in RIK's register belongs to. The register names the municipality and gives
    the station's number and name. A city's commission may list its city municipalities' stations under the city
    (Kostolac's under Požarevac, Sevojno's under Užice in 2026), each numbered within its own municipality, so one
    number can belong to two stations; or under a name the results don't use ("Ниш"). The station's name says
    which: the same number with the same name in a city municipality ("Градска општина") of the same district, or
    in a municipality whose name, in any election, contains the register's. Where nothing else fits, the decision
    stays where the register puts it, as before."""

    def __init__(self, codes: dict[str, str], stations=(), names: dict[str, set] | None = None):
        self.codes = dict(codes)  # municipality key → code
        self.names: dict[str, str] = {}  # station key → its name in the results
        self.numbered: dict[str, list[str]] = {}  # station number → station keys
        self.district: dict[str, str] = {}  # municipality code → district code
        self.city_part: set[str] = set()  # codes of city municipalities, which a city's commission may list
        self.aliases: dict[str, set] = {}  # municipality code → keys of every name it had
        for key, code in self.codes.items():
            self.aliases.setdefault(code, set()).add(key)
        for code, keys in (names or {}).items():
            self.aliases.setdefault(code, set()).update(keys)
        for st in stations:
            self.names[st.key] = st.name
            self.numbered.setdefault(st.number, []).append(st.key)
            self.district[st.municipality_code] = st.district_code
            if latin(st.municipality).upper().startswith("GRADSKA OPŠTINA"):
                self.city_part.add(st.municipality_code)

    def place(self, municipality: str, number: str, name: str = "") -> tuple[str | None, str]:
        """(station key or None, how): direct, moved (to another municipality of the district), named (found by
        the register's municipality name in another one's), as listed (the names differ and nothing else fits),
        or why not: no number, no such station, unknown municipality."""
        mkey = municipality_key(municipality)
        code = self.codes.get(mkey)
        if not number:
            return None, "no number"
        own = f"{code}/{number}" if code else None
        known = own is not None and (not self.names or own in self.names)  # a station of this election
        if known and (not name or not self.names or same_station(self.names[own], name)):
            return own, "direct"
        if name:
            def near(key: str) -> bool:
                c = key.split("/", 1)[0]
                if code:
                    return c != code and c in self.city_part and self.district.get(c) == self.district.get(code)
                return len(mkey) >= 3 and any(mkey in a for a in self.aliases.get(c, ()))
            found = [k for k in self.numbered.get(number, []) if near(k) and same_station(self.names[k], name)]
            if len(found) == 1:
                return found[0], "moved" if code else "named"
        if known:
            return own, "as listed"  # the names differ, and no other station fits
        return None, "no such station" if code else "unknown municipality"


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


def plan(round_dir: Path, round_id: str, rik_type: int, stations, client, log=print,
         retry_unparsed: bool = False, reindex: bool = False) -> dict:
    """Index the round's board decisions and say which to read: {"round", "whole", "index", "todo"}.

    The whole register is paged through unless the last run read everything and kept every decision's link, or
    with reindex (after the rules for placing decisions changed); otherwise older unread decisions (or links) deep
    in the register would be missed. `stations` is a Placer, or a dict from a municipality key (see
    municipality_key) to its code in the results file. Nothing here holds a name of a person: the log names
    municipalities only."""
    from collections import Counter
    placer = stations if isinstance(stations, Placer) else Placer(stations)
    store = load_store(round_dir)
    known = store.get("docs", {})
    whole = reindex or not store.get("complete") or any("u" not in d for d in known.values())
    docs = fetch_index(client, round_id, rik_type, frozenset() if whole else frozenset(known), log)
    index, todo = [], []
    how: Counter = Counter()
    unplaced: Counter = Counter()
    moved: Counter = Counter()
    for d in docs:
        key, why = placer.place(d.municipality, d.station, d.station_name)
        how[why] += 1
        if key is None:
            unplaced[(d.municipality, why, "empty" if not d.station_name and not d.station else
                      re.sub(r"[^\W\d_]+", "x", f"{d.station} - {d.station_name}")[:40])] += 1
        elif why in ("moved", "named", "as listed"):
            moved[(d.municipality, why, key.split("/")[0])] += 1
        index.append({"id": d.id, "s": key, "k": d.kind, "r": d.repeat, "t": d.published, "u": link_path(d.url)})
        entry = known.get(d.id)
        if d.kind == "extended" and (entry is None or entry.get("slots") is None
                                     or (retry_unparsed and entry.get("unparsed"))):
            todo.append({"id": d.id, "s": key, "station": d.station, "kind": d.kind, "repeat": d.repeat,
                         "published": d.published, "url": d.url})
    if retry_unparsed:  # unreadable decisions deeper in the register than this pass went, read again by their link
        listed = {d["id"] for d in todo}
        for i, entry in sorted(known.items()):
            if i not in listed and entry.get("k") == "extended" and entry.get("unparsed") and entry.get("u"):
                todo.append({"id": i, "s": entry.get("s"), "station": (entry.get("s") or "/").split("/")[1],
                             "kind": "extended", "repeat": bool(entry.get("r")), "published": entry.get("t") or "",
                             "url": RIK_PUBLIC.rstrip("/") + entry["u"]})
    log(f"{len(docs)} decisions indexed, {len(todo)} to read; placed: "
        + ", ".join(f"{why} {n}" for why, n in how.most_common()))
    for (municipality, why, code), n in moved.most_common(30):  # e.g. a city's commission listing its parts
        log(f"  {why}: {municipality!r} → {code}: {n}")
    for (municipality, why, title), n in unplaced.most_common(30):  # titles with every word masked
        log(f"  not placed ({why}): {municipality!r}, title like {title!r}: {n}")
    return {"round": round_id, "whole": whole, "index": index, "todo": todo}


def apply_index(store: dict, planned: dict) -> None:
    """Record what the register lists: every decision's link, and the kind of those not read with OCR."""
    known = store.setdefault("docs", {})
    for e in planned["index"]:
        entry = known.get(e["id"])
        if entry is not None:
            entry["u"] = e["u"]
            if e["s"]:  # where the register puts it, as the current rules place it; read with OCR or not
                entry["s"] = e["s"]
            if entry.get("slots") is None:  # not read with OCR: the register's listing is all that is kept
                entry.update({"k": e["k"], "r": e["r"]})
        elif e["k"] != "extended":
            known[e["id"]] = {"s": e["s"], "k": e["k"], "r": e["r"], "t": e["t"], "u": e["u"]}
    if planned["whole"]:
        for entry in known.values():
            entry.setdefault("u", "")  # no longer in RIK's register: nothing to link to
    store["indexed"] = len(set(known) | {e["id"] for e in planned["index"]})


def read(todo: list[dict], contestants: list[dict], base: str, workers: int = 4, budget_seconds: float = 5 * 3600,
         log=print, diagnose: int = 0, every: int = 200, progress=None) -> dict:
    """Read decisions with OCR, in worker processes: {"results": {id: what is kept}, "failed": [ids], "left": n}.

    No new decision is started after budget_seconds. progress(results) is called every `every` decisions."""
    import time
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

    started = time.monotonic()
    items = [({"municipality": "", "title": "", "decision": "", **{k: d[k] for k in
                ("id", "station", "kind", "repeat", "published", "url")}}, contestants, d["s"], base, diagnose > 0)
             for d in todo]
    results: dict[str, dict] = {}
    failed: list[str] = []
    unparsed = shown = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending, queue = set(), iter(items)
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
                    results[did] = result
                else:
                    failed.append(did)
                    log(f"could not read decision {did}: {error}")
                if (len(results) + len(failed)) % every == 0:
                    log(f"read {len(results)}, failed {len(failed)}")
                    if progress:
                        progress(results)
    left = len(items) - len(results) - len(failed)
    log(f"read {len(results)} (unreadable {unparsed}), failed {len(failed)}, left {left}")
    return {"results": results, "failed": failed, "left": left, "unparsed": unparsed}


def apply_results(store: dict, results: dict) -> None:
    store.setdefault("docs", {}).update(results)


def run(round_dir: Path, round_id: str, rik_type: int, contestants: list[dict], stations, client,
        workers: int = 4, budget_seconds: float = 5 * 3600, limit: int | None = None, log=print,
        save_every: int = 200, checkpoint=None, diagnose: int = 0, retry_unparsed: bool = False,
        reindex: bool = False) -> dict:
    """Index the round's board decisions and read the ones not yet read, in this process's workers (the boards
    workflow splits the reading across several jobs instead: plan, read, merge)."""
    planned = plan(round_dir, round_id, rik_type, stations, client, log, retry_unparsed, reindex)
    store = load_store(round_dir)
    apply_index(store, planned)
    todo = planned["todo"] if limit is None else planned["todo"][:limit]

    def progress(results: dict) -> None:
        apply_results(store, results)
        save_store(round_dir, store)
        if checkpoint:
            checkpoint()

    got = read(todo, contestants, client.base, workers, budget_seconds, log, diagnose, save_every, progress)
    apply_results(store, got["results"])
    store["complete"] = limit is None and not got["failed"] and not got["left"]
    save_store(round_dir, store)
    return {"indexed": len(planned["index"]), "read": len(got["results"]), "failed": len(got["failed"]),
            "unparsed": got["unparsed"], "left": got["left"]}
