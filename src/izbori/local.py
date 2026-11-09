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
          path_has: str = "") -> None:
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
            text = text_of(fetch(u), u)
        except Exception as e:  # noqa: BLE001 - one document down must not stop the probe
            log(f"[{k}] {shape(name, 120)}: {type(e).__name__}")
            continue
        log(f"[{k}] {docs[u]['k']} {urllib.parse.urlsplit(u).path.rsplit('/', 1)[0]}/{shape(name, 120)} "
            f"({len(text)} characters)\n{shape(text)}\n")
