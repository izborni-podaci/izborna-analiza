"""A weekly look at the municipalities' own web sites for the electoral commissions' documents.

The law has local electoral commissions publish their acts on the web; most put them on the municipality's site,
not in RIK's register. `data/municipal_sites.csv` lists each municipality's site (the domain of the commission's
e-mail in RIK's address book of local commissions; a webmail address leaves the site to find by hand). `izbori
watch` visits each site's front page, the pages linked from it that speak of elections or the commission, and the
site's own search for polling stations and polling boards (most are WordPress), and keeps the links to documents
(.pdf, .doc, .docx) whose link text or file name is about polling stations, polling boards or the commission —
in `data/municipal_docs.json`: link, municipality, kind, when first seen. No text of a document is kept, and
link texts are not copied (a title can name a person); the kind is told from keywords. A new "stations" document
is a candidate for `data/station_lists.csv`, logged with the line to add.
"""
from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from izbori import jsonfile
from izbori.translit import latin

SITES_FILE = "municipal_sites.csv"
STORE = "municipal_docs.json"
AGENT = "izborna-analiza (https://github.com/izborni-podaci/izborna-analiza)"
DOC_EXT = (".pdf", ".doc", ".docx")
MAX_PAGES = 60  # per site and visit
PAUSE = 0.7  # seconds between requests to one site
SEARCHES = ("бирачких места", "biračkih mesta", "бирачки одбор", "birački odbor")

# what a link must speak of to be followed (a page) or kept (a document); compared in folded Latin
PAGE_WORDS = ("izbor", "komisij", "birack", "glasan")
KINDS = (  # first match wins
    ("stations", ("birack", "mest"), ("odredjivanj", "utvrdjivanj", "odluka", "resenj")),
    ("boards", ("birack", "odbor"), ()),
    ("commission", ("izborn", "komisij"), ()),
)


def fold(text: str) -> str:
    s = latin(text or "").replace("Đ", "Dj").replace("đ", "dj").lower()
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s)


def kind_of(text: str) -> str | None:
    """The kind of document a link's text and file name point to, or None when it is not the commission's."""
    f = fold(text)
    for kind, must, any_of in KINDS:
        if all(w in f for w in must) and (not any_of or any(w in f for w in any_of)):
            return kind
    return None


def load_sites(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(f)]


class Links(HTMLParser):
    """Every link of a page: (href, text)."""

    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def links_of(html: str, base: str) -> list[tuple[str, str]]:
    p = Links()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - broken HTML: keep what was parsed
        pass
    out = []
    for href, text in p.links:
        if not href or href.startswith(("mailto:", "javascript:", "#", "tel:")):
            continue
        out.append((urllib.parse.urljoin(base, href.strip()), text))
    return out


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Language": "sr"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.headers.get("Content-Type", "").split(";")[0] not in ("text/html", "application/xhtml+xml", ""):
            return ""
        data = r.read(2_000_000)
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def crawl(domain: str, log=None, fetcher=fetch, sleep=time.sleep) -> dict[str, str]:
    """The commission's documents on one site: url → kind. The front page, then the pages it links to about
    elections or the commission (one level), then the site's search for each phrase in SEARCHES."""
    host = domain.lower()
    # the front page: https, then www, then plain http (old sites)
    roots = [f"https://{domain}/", f"https://www.{domain}/", f"http://{domain}/", f"http://www.{domain}/"]
    found: dict[str, str] = {}
    seen: set[str] = set()
    root = None
    for r in roots:
        try:
            html = fetcher(r)
            root = r
            break
        except Exception as e:  # noqa: BLE001 - try the next spelling
            err = type(e).__name__
    if root is None:
        if log:
            log(f"{domain}: {err}")
        return found
    sleep(PAUSE)
    queue: list[tuple[str, int, str | None]] = [(f"{root}?s={urllib.parse.quote(q)}", 2, None) for q in SEARCHES]
    pages = 1

    def take(html: str, url: str, depth: int) -> None:
        for href, text in links_of(html, url):
            u = urllib.parse.urlsplit(href)
            if u.netloc.lower().removeprefix("www.") != host.removeprefix("www."):
                continue
            path = u.path.lower()
            about = fold(text + " " + urllib.parse.unquote(path))
            if path.endswith(DOC_EXT):
                kind = kind_of(text + " " + urllib.parse.unquote(path.rsplit("/", 1)[-1]))
                if kind and href not in found:
                    found[href] = kind
            elif depth < 2 and any(w in about for w in PAGE_WORDS):
                # an election page, and the pages it links to about elections ("Избори" → "Избори 2026")
                queue.append((href, depth + 1, None))

    take(html, root, 0)
    while queue and pages < MAX_PAGES:
        url, depth, _ = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html = fetcher(url)
        except Exception:  # noqa: BLE001 - a page down must not stop the site
            continue
        pages += 1
        sleep(PAUSE)
        take(html, url, depth)
    return found


def load_store(root: Path) -> dict:
    p = Path(root) / STORE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"docs": {}}


def save_store(root: Path, store: dict) -> None:
    (Path(root) / STORE).write_text(jsonfile.dumps(store, "docs"), encoding="utf-8")


def run(root: Path, today: str, log=print, fetcher=fetch, sleep=time.sleep, only: set | None = None) -> int:
    """Visit every site with a domain; keep new documents; return how many are new."""
    sites = [s for s in load_sites(Path(root) / SITES_FILE) if s.get("domain")]
    if only:
        sites = [s for s in sites if s["municipality_code"] in only]
    store = load_store(root)
    new = 0
    for s in sites:
        found = crawl(s["domain"], log, fetcher, sleep)
        fresh = {u: k for u, k in found.items() if u not in store["docs"]}
        for u, k in fresh.items():
            store["docs"][u] = {"m": s["municipality_code"], "k": k, "seen": today}
        new += len(fresh)
        if fresh:
            log(f"{s['municipality_code']} {latin(s['name'])}: {len(fresh)} new ({', '.join(sorted(set(fresh.values())))})")
            for u, k in fresh.items():
                if k == "stations":
                    log(f"  candidate for station_lists.csv: <round>,{s['municipality_code']},{u},\"found on the site\"")
    save_store(root, store)
    log(f"{len(sites)} sites visited, {new} new documents, {len(store['docs'])} kept")
    return new
