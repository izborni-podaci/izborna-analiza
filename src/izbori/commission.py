"""The documents of each municipality's electoral commission: minutes of its sessions (where objections are
decided), reports on the results, decisions, resolutions and notices.

Source: RIK's register of additional documents, type 1, for the round. Each document is kept by its link, the
kind RIK gives it and its upload time, never by its title: commissions write the titles, and a title may name a
person. RIK's own documents (listed under "РИК") are left out; they belong to no municipality.

Kept per round in data/rounds/<id>/commission.json:
    {"docs": {"<id>": {"m": municipality code, "c": kind, "t": upload time (unix), "u": path}}, "complete": bool}"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from izbori.boards import doc_id, last_page, link_path, municipality_key
from izbori.config import RIK_PUBLIC
from izbori.i18n import BELGRADE

FILE = "commission.json"
DOC_TYPE = 1  # RIK's number for the commissions' documents in its register of additional documents
# RIK's kinds, in the order the page lists them
KINDS = {"ЗАПИСНИЦИ СА СЕДНИЦА": "session", "ИЗВЕШТАЈ": "report", "РЕШЕЊЕ": "decision", "ОДЛУКА": "resolution",
         "ИНФОРМАЦИЈА": "notice"}
ORDER = ["session", "report", "decision", "resolution", "notice", "other"]


def kind(decision_type: str) -> str:
    text = " ".join((decision_type or "").upper().split())
    return next((k for label, k in KINDS.items() if label in text), "other")


def parse_records(records: list[dict], codes: dict[str, str]) -> list[tuple[str, dict]]:
    """(id, what is kept) for each record of a municipality; codes maps a municipality key to its code."""
    out = []
    for r in records:
        links = re.findall(r'href="([^"]+)"', " ".join(r.get("extfiles_link") or []))
        name = (r.get("municipality_display_name") or "").strip()
        if not links or name.upper() in ("РИК", "RIK"):
            continue
        out.append((doc_id(links[0]), {"m": codes.get(municipality_key(name), ""), "c": kind(r.get("decision_type")),
                                       "t": str(r.get("datetime") or ""), "u": link_path(links[0])}))
    return out


def query(page: int, round_id: str, rik_type: int) -> str:
    from izbori.boards import index_query
    return index_query(page, round_id, rik_type, document_type=DOC_TYPE)


def fetch(client, round_id: str, rik_type: int, codes: dict[str, str], known: frozenset = frozenset(), log=print,
          threads: int = 3) -> list[tuple[str, dict]]:
    """The round's commission documents, newest first. Once some are known, paging stops at the first page with
    nothing new (RIK lists the newest first)."""
    from concurrent.futures import ThreadPoolExecutor

    def page(n: int) -> list[tuple[str, dict]]:
        return parse_records((client.get_json(query(n, round_id, rik_type)) or {}).get("records") or [], codes)

    first = client.get_json(query(1, round_id, rik_type)) or {}
    pages = last_page(first.get("pagination", ""))
    docs = parse_records(first.get("records") or [], codes)
    if known:
        n = 1
        while n < pages and not all(i in known for i, _ in docs[-10:]):
            n += 1
            docs.extend(page(n))
    else:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            for batch in ex.map(page, range(2, pages + 1)):
                docs.extend(batch)
    log(f"{round_id}: {len(docs)} commission documents listed ({pages} pages)")
    return docs


def path(round_dir: Path) -> Path:
    return Path(round_dir) / FILE


def load_store(round_dir: Path) -> dict:
    p = path(round_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"docs": {}}


def save_store(round_dir: Path, store: dict) -> bool:
    p = path(round_dir)
    text = json.dumps(store, ensure_ascii=False, indent=0, sort_keys=True) + "\n"
    if p.exists() and p.read_text(encoding="utf-8") == text:
        return False
    p.write_text(text, encoding="utf-8")
    return True


def update(client, round_dir: Path, round_id: str, rik_type: int, codes: dict[str, str], log=print) -> int:
    """Read what is new in the register; how many documents were added."""
    store = load_store(round_dir)
    known = store.setdefault("docs", {})
    found = fetch(client, round_id, rik_type, codes, frozenset(known) if store.get("complete") else frozenset(), log)
    added = 0
    for i, d in found:
        if i not in known:
            added += 1
        known[i] = d
    store["complete"] = True
    save_store(round_dir, store)
    return added


def by_municipality(store: dict) -> dict[str, list[dict]]:
    """Per municipality code, its documents grouped by kind: [{"kind", "docs": [{"url", "day", "n"}]}], each kind's
    documents oldest first, numbered when several share a day."""
    grouped: dict[str, dict[str, list]] = {}
    for d in store.get("docs", {}).values():
        if not d.get("m") or not d.get("u"):
            continue
        when = datetime.fromtimestamp(int(d["t"]), tz=BELGRADE) if (d.get("t") or "").isdigit() else None
        url = d["u"] if d["u"].startswith("http") else RIK_PUBLIC.rstrip("/") + d["u"]
        grouped.setdefault(d["m"], {}).setdefault(d.get("c") or "other", []).append((when, url))
    out = {}
    for code, kinds in grouped.items():
        rows = []
        for k in sorted(kinds, key=ORDER.index):
            items = sorted(kinds[k], key=lambda x: (x[0] is None, x[0] or datetime.min.replace(tzinfo=BELGRADE), x[1]))
            docs, per_day = [], {}
            for when, url in items:
                day = when.date().isoformat() if when else ""
                per_day[day] = per_day.get(day, 0) + 1
                docs.append({"url": url, "day": day, "n": per_day[day]})
            same = {day for day, n in per_day.items() if n > 1}
            for d in docs:
                d["n"] = d["n"] if d["day"] in same else 0
            rows.append({"kind": k, "docs": docs})
        out[code] = rows
    return out
