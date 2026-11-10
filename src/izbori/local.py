"""Local elections from the municipalities' own documents (9 Nov 2026, Pančevo first).

RIK holds no local elections: the municipal electoral commission appoints the polling boards, proclaims the lists
and publishes the results, on the municipality's site. `watch.py` finds those documents (data/municipal_docs.json);
this module reads them. First step, `izbori local --probe CODE`: download a municipality's documents of one kind
and log each one's layout with every word that isn't a word of the forms masked (boards.shape), so the readers can
be written for real documents without a name reaching a log.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request

from izbori import boards, watch

# words of the commissions' forms, shown in a probe's layout; anything else is masked
FORM_WORDS = {
    "записник", "извештај", "извештају", "резултат", "резултати", "резултатима", "укупним", "укупни", "гласова",
    "гласало", "гласали", "гласачких", "бирача", "бирачких", "уписаних", "важећих", "неважећих", "листића", "листа",
    "листи", "листе", "изборне", "изборних", "изборна", "проглашењу", "проглашавању", "збирној", "кандидата",
    "одборника", "одборнике", "скупштине", "скупштину", "града", "општине", "утврђивању", "одређивању", "места",
    "место", "одбора", "одбор", "бирачки", "бирачког", "решење", "одлука", "одлуку", "члан", "заменик", "предлог",
    "подносиоца", "сталном", "проширеном", "саставу", "мандата", "мандати", "расподели", "број", "бм", "на", "и",
    "zapisnik", "izveštaj", "rezultat", "rezultati", "rezultatima", "ukupnim", "glasova", "birača", "biračkih",
    "upisanih", "važećih", "nevažećih", "listića", "lista", "liste", "listi", "izborne", "izborna", "proglašenju",
    "zbirnoj", "kandidata", "odbornika", "skupštine", "grada", "opštine", "mesta", "mesto", "odbora", "birački",
    "rešenje", "odluka", "član", "zamenik", "predlog", "mandata", "broj",
}
LETTERS_WORD = re.compile(r"[A-Za-zА-Яа-яЂђЈјЉљЊњЋћЏџČčĆćŠšŽžĐđ]+")


def shape(text: str, limit: int = 1200) -> str:
    """A document's layout with every word that isn't a form's word masked (no name is shown); numbers stay."""
    def mask(m: re.Match) -> str:
        w = m.group(0)
        return w if w.lower() in FORM_WORDS or w.lower() in boards.KEEP_WORDS else "x" * min(len(w), 3)
    return LETTERS_WORD.sub(mask, re.sub(r"[ \t]+", " ", text))[:limit]


def download(url: str, timeout: int = 90) -> bytes:
    url = urllib.parse.quote(url, safe="/:?&=%@+,;~!$'()*")  # Cyrillic in a link
    req = urllib.request.Request(url, headers={"User-Agent": watch.AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(30_000_000)


def text_of(data: bytes, url: str, pages: int = 2) -> str:
    if url.lower().endswith(".docx") or data[:2] == b"PK":
        from izbori.stationlist import docx_text
        return docx_text(data)
    if not data.startswith(b"%PDF"):
        return ""
    text = boards.pdf_text(data, max_pages=pages)
    if len(re.findall(r"[А-Яа-яA-Za-z]", text)) < 100:
        text = boards.pdf_text(data, max_pages=pages, ocr=True)
    return text


def probe(docs: dict, code: str, kind: str | None = None, limit: int = 40, log=print, fetch=download,
          path_has: str = "", pages: int = 2, chars: int = 1200) -> None:
    """Log the masked layout of a municipality's documents (of one kind), the folders they sit in first."""
    mine = sorted(u for u, v in docs.items() if v["m"] == code and (not kind or v["k"] == kind)
                  and path_has in urllib.parse.unquote(u))
    folders: dict[str, int] = {}
    for u in mine:
        folders[urllib.parse.urlsplit(u).path.rsplit("/", 1)[0]] = folders.get(urllib.parse.urlsplit(u).path.rsplit("/", 1)[0], 0) + 1
    log(f"{code}: {len(mine)} documents" + (f" of kind {kind}" if kind else "") + "; by folder: "
        + ", ".join(f"{f} {n}" for f, n in sorted(folders.items())))
    for k, u in enumerate(mine[:limit], 1):
        name = urllib.parse.unquote(u.rsplit("/", 1)[-1])
        try:
            text = text_of(fetch(u), u, pages=pages)
        except Exception as e:  # noqa: BLE001 - one document down must not stop the probe
            log(f"[{k}] {shape(name, 120)}: {type(e).__name__}")
            continue
        log(f"[{k}] {docs[u]['k']} {urllib.parse.urlsplit(u).path.rsplit('/', 1)[0]}/{shape(name, 120)} "
            f"({len(text)} characters)\n{shape(text, chars)}\n")


# --- what a document is, from its first page ---------------------------------------------------------------------
# A link's text or file name says little (Pančevo's "board" documents were the boards' minutes of the vote), so a
# document is told by the words of its form on the first page, in folded Latin (watch.fold). Kept per link in
# data/local_docs.json: the kind, which election it belongs to and that election's day where the page gives it;
# nothing of the text. Kinds, first match wins:
KINDS = (
    ("minutes", (("zapisnik",), ("o radu birackog odbora", "rad birackog odbora", "birackog odbora"))),
    ("results", (("izvestaj", "zapisnik", "rezultat"), ("o ukupnim rezultatima", "ukupni rezultati", "utvrdjivanju rezultata", "rezultatima izbora"))),
    ("lists", (("zbirn", "proglas", "lista kandidata"), ("izborn", "list"))),
    ("boards", (("resenje", "resenja"), ("imenovanju", "razresenju", "imenovanje"))),
    ("stations", (("odluk", "resenje"), ("odredjivanju birackih mesta", "utvrdjivanju birackih mesta", "birackih mesta"))),
    ("session", (("zapisnik",), ("sednic",))),
)
ELECTIONS = (  # which election, by what the form says it is for
    ("local", ("odbornika", "odbornike", "skupstine opstine", "skupstine grada", "skupstinu opstine", "skupstinu grada",
               "gradske opstine")),
    ("provincial", ("pokrajine", "ap vojvodine", "autonomne pokrajine")),
    ("presidential", ("predsednika republike",)),
    ("parliamentary", ("narodnih poslanika", "narodne poslanike", "narodni poslanici")),
)
MONTHS = {"januar": 1, "februar": 2, "mart": 3, "april": 4, "maj": 5, "jun": 6, "jul": 7, "avgust": 8,
          "septemb": 9, "oktob": 10, "novemb": 11, "decemb": 12}  # stems: "oktobra", "decembra"
DATE = re.compile(r"(\d{1,2})\s*\.\s*(?:(\d{1,2})\s*\.|(" + "|".join(MONTHS) + r")[a-z]*)\s*(20\d\d)")
STORE = "local_docs.json"


def classify(text: str) -> dict:
    """{"k": kind or "other", "e": election or None, "d": its day (YYYY-MM-DD) or None} from a first page."""
    f = watch.fold(text)
    # a title set in spaced capitals ("Р Е Ш Е Њ Е") read as one word
    f = re.sub(r"(?<![a-z])((?:[a-z]{1,2} ){3,}[a-z]{1,2})(?![a-z])", lambda m: m.group(1).replace(" ", ""), f)
    kind = "other"
    for k, (first, second) in KINDS:
        if any(w in f for w in first) and any(w in f for w in second):
            kind = k
            break
    election = next((e for e, words in ELECTIONS if any(w in f for w in words)), None)
    return {"k": kind, "e": election, "d": election_day(f)}


def election_day(folded: str) -> str | None:
    """The day of the election a form is about: the first date within a short reach after "izbor" ("izbora
    održanih 17. decembra 2023", "izbori raspisani za 2.6.2024"); None when no such date."""
    for m in re.finditer(r"izbor", folded):
        d = DATE.search(folded, m.end(), m.end() + 160)
        if d:
            day = int(d.group(1))
            month = int(d.group(2)) if d.group(2) else MONTHS[d.group(3)]
            if 1 <= day <= 31 and 1 <= month <= 12:
                return f"{d.group(4)}-{month:02d}-{day:02d}"
    return None


def first_page(url: str, fetch=None) -> str:
    data = (fetch or download)(url)
    return text_of(data, url, pages=1)


def _one(url: str) -> tuple[str, dict | None, str | None]:
    try:
        return url, classify(first_page(url)), None
    except Exception as e:  # noqa: BLE001 - a document down: left for the next run
        return url, None, type(e).__name__


def load_store(root) -> dict:
    import json
    from pathlib import Path
    p = Path(root) / STORE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"docs": {}}


def save_store(root, store: dict) -> None:
    from pathlib import Path
    from izbori import jsonfile
    (Path(root) / STORE).write_text(jsonfile.dumps(store, "docs"), encoding="utf-8")


def run_classify(root, codes: set | None = None, log=print, workers: int = 4, budget_seconds: float = 4 * 3600,
                 one=_one) -> int:
    """Classify every document the watch found and this store lacks (of the given municipalities); saved as it
    goes, so a run cut short by its budget resumes. Returns how many were classified."""
    import time as _time
    from concurrent.futures import ProcessPoolExecutor
    docs = watch.load_store(root)["docs"]
    store = load_store(root)
    todo = [u for u, v in sorted(docs.items()) if u not in store["docs"] and (not codes or v["m"] in codes)]
    log(f"{len(todo)} documents to classify")
    start, done = _time.time(), 0
    pool = ProcessPoolExecutor(workers) if workers > 1 else None
    try:
        results = pool.map(one, todo) if pool else map(one, todo)
        for url, got, err in results:
            if got:
                store["docs"][url] = {"m": docs[url]["m"], **got}
                done += 1
            if done and done % 100 == 0:
                save_store(root, store)
                log(f"{done} classified")
            if _time.time() - start > budget_seconds:
                log("time budget used; the next run continues")
                break
    finally:
        if pool:
            pool.shutdown(cancel_futures=True)
    save_store(root, store)
    from collections import Counter
    mine = [v for v in store["docs"].values() if not codes or v["m"] in codes]
    log(f"{done} classified now; kinds: {dict(Counter(v['k'] for v in mine))}; "
        f"elections: {dict(Counter((v['e'], v['d']) for v in mine).most_common(12))}")
    return done
