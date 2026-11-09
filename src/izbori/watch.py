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
# a browser-like start, as some municipal sites refuse a bare client name (403), and who we are after it
AGENT = "Mozilla/5.0 (compatible; izborna-analiza; +https://izbornipodaci.rs)"
DOC_EXT = (".pdf", ".doc", ".docx")
MAX_PAGES = 100  # per site and visit
DEPTH = 3  # links followed from the front page: Izbori → Izbori 2026 → Odluke
PAUSE = 0.5  # seconds between requests to one site
SEARCHES = ("бирачких места", "biračkih mesta", "бирачки одбор", "birački odbor")

# what a link must speak of to be followed (a page) or kept (a document); compared in folded Latin
PAGE_WORDS = ("izbor", "komisij", "birack", "glasan", "dokument", "oglasn", "sluzben", "odluk", "akti")
# the site's own index of uploads where it has one: WordPress's media search (uploads by title), and the sitemaps
MEDIA_SEARCHES = ("бирачк", "birack", "biračk", "изборн", "izborn", "одбор")
SITEMAPS = ("wp-sitemap.xml", "sitemap.xml", "sitemap_index.xml")
MAX_SITEMAPS = 25
KINDS = (  # first match wins
    ("stations", ("birack", "mest"), ("odredjivanj", "utvrdjivanj", "odluka", "resenj")),
    ("boards", ("birack", "odbor"), ()),
    ("commission", ("izborn", "komisij"), ()),
    # what only the local commission publishes for a local election: its results and the lists it proclaimed
    ("results", ("rezultat",), ("izbor", "odborni", "glasan", "zapisnik", "izvestaj")),
    ("lists", ("list",), ("proglas", "zbirn", "kandidat", "odborni")),
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
        try:  # a broken link ("http://[…") must not stop the site, let alone the run (9 Nov 2026, after 2.5 hours)
            url = urllib.parse.urljoin(base, href.strip())
            urllib.parse.urlsplit(url)
        except ValueError:
            continue
        out.append((url, text))
    return out


TEXT_TYPES = ("text/html", "application/xhtml+xml", "application/json", "application/xml", "text/xml", "")


def fetch(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Language": "sr"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.headers.get("Content-Type", "").split(";")[0] not in TEXT_TYPES:
            return ""
        data = r.read(2_000_000)
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def why(e: Exception) -> str:
    """A failure in a few words for the log: the kind and its reason (a certificate, a timeout, a name not found)."""
    reason = getattr(e, "reason", None) or getattr(e, "code", None) or ""
    return f"{type(e).__name__} {str(reason)[:80]}".strip()


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
            err = why(e)
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
            elif depth < DEPTH and any(w in about for w in PAGE_WORDS):
                # an election page, and the pages it links to about elections ("Избори" → "Избори 2026" → "Одлуке")
                queue.append((href, depth + 1, None))

    take(html, root, 0)
    # the site's own indexes: WordPress's search of its uploads, then its sitemaps
    for q in MEDIA_SEARCHES:
        try:
            items = json.loads(fetcher(f"{root}wp-json/wp/v2/media?search={urllib.parse.quote(q)}&per_page=100"
                                       "&_fields=source_url,title") or "[]")
        except Exception:  # noqa: BLE001 - not WordPress, or its API closed: the pages remain
            break
        pages += 1
        sleep(PAUSE)
        if not isinstance(items, list):
            break
        for it in items:
            src = (it or {}).get("source_url") or ""
            title = ((it or {}).get("title") or {}).get("rendered") or ""
            u = urllib.parse.urlsplit(src)
            if u.path.lower().endswith(DOC_EXT) and u.netloc.lower().removeprefix("www.") == host.removeprefix("www."):
                kind = kind_of(title + " " + urllib.parse.unquote(u.path.rsplit("/", 1)[-1]))
                if kind and src not in found:
                    found[src] = kind
    maps, read_maps = [f"{root}{m}" for m in SITEMAPS], 0
    while maps and read_maps < MAX_SITEMAPS:
        sm = maps.pop(0)
        try:
            xml = fetcher(sm)
        except Exception:  # noqa: BLE001 - no such sitemap
            continue
        read_maps += 1
        sleep(PAUSE)
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml or ""):
            loc = loc.replace("&amp;", "&")
            path = urllib.parse.urlsplit(loc).path.lower()
            if path.endswith(".xml"):
                if loc not in maps:
                    maps.append(loc)
            elif path.endswith(DOC_EXT):
                kind = kind_of(urllib.parse.unquote(path.rsplit("/", 1)[-1]))
                if kind and loc not in found:
                    found[loc] = kind
            elif any(w in fold(urllib.parse.unquote(path)) for w in ("izbor", "birack", "komisij")):
                queue.append((loc, 1, None))
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


def variants(domain: str) -> list[str]:
    """Other spellings of a municipality's site, for when the commission's e-mail domain doesn't answer: Valjevo's
    mail is at valjevo.org.rs, its site at valjevo.rs. The same name under .rs, .org.rs and .ls.gov.rs."""
    d = domain.lower().removeprefix("www.")
    for tail in (".ls.gov.rs", ".org.rs", ".gov.rs", ".rs"):
        if d.endswith(tail):
            base = d[: -len(tail)]
            break
    else:
        return []
    if "." in base:  # grad.zrenjanin.rs, obrenovac.bg.ls.gov.rs: a name inside another; left as it is
        return []
    return [f"{base}{t}" for t in (".rs", ".org.rs", ".ls.gov.rs", ".gov.rs") if f"{base}{t}" != d]


def answers(domain: str, fetcher=fetch) -> bool:
    for r in (f"https://{domain}/", f"https://www.{domain}/", f"http://{domain}/", f"http://www.{domain}/"):
        try:
            fetcher(r)
            return True
        except Exception:  # noqa: BLE001 - the next spelling
            continue
    return False


def save_sites(path: Path, sites: list[dict]) -> None:
    cols = list(sites[0].keys()) if sites else ["municipality_code", "name", "domain", "note"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(sites)


def run(root: Path, today: str, log=print, fetcher=fetch, sleep=time.sleep, only: set | None = None,
        others_only: bool = False) -> int:
    """Visit every site with a domain; keep new documents; return how many are new. A site whose domain doesn't
    answer is looked for under its other spellings (`variants`); one that answers replaces it in
    municipal_sites.csv, the old one named in the note. others_only: skip the domain itself (just tried by another
    run) and look only under the other spellings."""
    all_sites = load_sites(Path(root) / SITES_FILE)
    sites = [s for s in all_sites if s.get("domain")]
    if only:
        sites = [s for s in sites if s["municipality_code"] in only]
    store = load_store(root)
    new, moved = 0, False
    for s in sites:
        if others_only or not answers(s["domain"], fetcher):
            alt = next((v for v in variants(s["domain"]) if answers(v, fetcher)), None)
            if alt:
                log(f"{s['municipality_code']} {latin(s['name'])}: {s['domain']} doesn't answer, {alt} does")
                s["note"] = (s.get("note", "") + f"; was {s['domain']}, found by the watch {today}").strip("; ")
                s["domain"], moved = alt, True
            elif others_only:
                log(f"{s['municipality_code']} {latin(s['name'])}: no other spelling of {s['domain']} answers")
                continue
        try:
            found = crawl(s["domain"], log, fetcher, sleep)
        except Exception as e:  # noqa: BLE001 - one site's oddity must not lose the others' finds
            log(f"{s['municipality_code']} {latin(s['name'])}: stopped, {why(e)}")
            continue
        fresh = {u: k for u, k in found.items() if u not in store["docs"]}
        for u, k in fresh.items():
            store["docs"][u] = {"m": s["municipality_code"], "k": k, "seen": today}
        new += len(fresh)
        if fresh:
            save_store(root, store)  # as it goes: a run cut short keeps what it found
        if fresh:
            log(f"{s['municipality_code']} {latin(s['name'])}: {len(fresh)} new ({', '.join(sorted(set(fresh.values())))})")
            for u, k in fresh.items():
                if k == "stations":
                    log(f"  candidate for station_lists.csv: <round>,{s['municipality_code']},{u},\"found on the site\"")
    save_store(root, store)
    if moved:
        save_sites(Path(root) / SITES_FILE, all_sites)
    log(f"{len(sites)} sites visited, {new} new documents, {len(store['docs'])} kept")
    return new
