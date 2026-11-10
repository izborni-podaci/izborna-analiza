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


# --- the commission's report of results by polling station ------------------------------------------------------
# One row per station: number, registered, voted (circled in the register), ballots in the box, invalid, valid,
# then each list's votes in ballot order (Pančevo 2024: "1 1354 577 577 14 563 473 5 37 9 39"). OCR loses a digit
# or reads one as a sign ("|||" for 7, "1!" for 11, "|90" for 19), so a row is checked against itself: the lists
# add up to the valid votes, and the ballots in the box less the invalid ones are the valid votes. One unreadable
# cell in an equation is worked out from it; a row that still doesn't add up is set aside for a person, never guessed.
FIXED = 6  # number, registered, voted, ballots, invalid, valid
CELL_FIX = str.maketrans({"|": "1", "!": "1", "l": "1", "I": "1", "і": "1", "О": "0", "O": "0", "o": "0",
                          "о": "0", "S": "5", "B": "8", ")": "1", "]": "1", "%": "5"})


def cell(tok: str) -> int | None:
    t = tok.translate(CELL_FIX).strip(".,;:'`")
    return int(t) if t.isdigit() else None


def result_rows(text: str) -> tuple[int, list[dict], list[dict]]:
    """The lists' count, the rows read ({"n", "registered", "voted", "ballots", "invalid", "valid", "v": [...],
    "note"}) and the rows set aside ({"n", "why"}), from the text of a results report."""
    lines = []
    for line in text.replace("\r", "").split("\n"):
        toks = line.split()
        if len(toks) >= FIXED + 1 and sum(1 for t in toks if cell(t) is not None) >= len(toks) - 2:
            lines.append(toks)
    if not lines:
        return 0, [], []
    from collections import Counter
    k = Counter(len(t) - FIXED for t in lines).most_common(1)[0][0]
    rows, aside, expect = [], [], 1
    for toks in lines:
        if len(toks) != FIXED + k:
            continue
        cells = [cell(t) for t in toks]
        # the sequence decides a misread number ("37" for 57, "|||" for 7); a row OCR lost (one to three) is skipped
        n = cells[0] if cells[0] is not None and expect <= cells[0] <= expect + 3 else expect
        expect = n + 1
        reg, voted, box, invalid, valid = cells[1:FIXED]
        votes = cells[FIXED:]
        notes = []
        raw = {"registered": reg, "voted": voted, "ballots": box, "invalid": invalid, "valid": valid, "v": list(votes)}
        # the lists against the valid votes
        missing = [i for i, v in enumerate(votes) if v is None]
        if valid is None and not missing:
            valid = sum(votes)
            notes.append("valid from the lists")
        elif valid is not None and len(missing) == 1:
            votes[missing[0]] = valid - sum(v for v in votes if v is not None)
            notes.append(f"list {missing[0] + 1} from the valid votes")
        if valid is None or None in votes or votes[missing[0]] < 0 if missing else False:
            aside.append({"n": n, "why": "lists and valid votes unreadable", "raw": raw})
            continue
        if sum(votes) != valid:
            aside.append({"n": n, "why": f"lists add up to {sum(votes)}, valid votes read {valid}", "raw": raw})
            continue
        # ballots, invalid and valid
        if box is None and invalid is not None:
            box = valid + invalid
            notes.append("ballots from valid and invalid")
        elif invalid is None and box is not None:
            invalid = box - valid
            notes.append("invalid from ballots and valid")
        elif box is not None and invalid is not None and box - invalid != valid:
            # one of the two misread: the one that keeps ballots within the voters circled is kept
            if voted is not None and 0 <= voted - (valid + invalid) <= max(3, voted // 50):
                box = valid + invalid
                notes.append("ballots from valid and invalid")
            elif voted is not None and 0 <= box - valid <= max(3, box // 10) and box <= voted:
                invalid = box - valid
                notes.append("invalid from ballots and valid")
            else:
                aside.append({"n": n, "why": "ballots, invalid and valid votes don't agree", "raw": raw})
                continue
        if box is None or invalid is None or invalid < 0:
            aside.append({"n": n, "why": "ballots and invalid unreadable", "raw": raw})
            continue
        if voted is None or voted < box or voted > (reg or voted):
            if voted is not None and voted < box:  # "37" for 377: a digit lost
                notes.append("voted taken as the ballots (read lower than them)")
            elif voted is None:
                notes.append("voted taken as the ballots (unreadable)")
            voted = box if (voted is None or voted < box) else voted
        rows.append({"n": n, "registered": reg, "voted": voted, "ballots": box, "invalid": invalid, "valid": valid,
                     "v": votes, "note": "; ".join(notes)})
    return k, rows, aside


# --- a local election as a round of the archive -------------------------------------------------------------------
# What the readers make of a municipality's local election is written as a round in RIK's own format (results.csv,
# meta.json), so every page of the site treats it as it treats RIK's rounds. It is first a draft under
# data/local/<id>/, with the rows set aside and the lists' names as the commission's decisions print them, for a
# person to check; `--publish` moves it to data/rounds/<id>/.
DRAFTS = "local"
RESULT_COLUMNS = ["bm_uid", "bm_broj", "bm_naziv", "opstina", "sifra_opstine", "okrug_region", "sifra_okruga_regiona",
                  "upisani_biraci", "glasali_biraci", "listici_u_kutiji", "vazeci_glasovi", "nevazeci_listici",
                  "vreme_unosa_rezultata"]
LIST_NAME = re.compile(r"(?:изборн[ауе]\s+лист[ауе]|izborn[aue]\s+list[aue])\s*(?:под\s+називом\s*)?[„\"“«]\s*([^\n„\"“”»]{3,240}?)\s*[“”\"»]",
                       re.I)


def round_id(code: str, day: str) -> str:
    return f"L{code}-{day.replace('-', '')}"


def stations_like(root, code: str, n: int, day: str):
    """The stations of the municipality in the archived round nearest in time with as many stations: their names
    and district, by number (a local election uses the polling stations of the elections around it)."""
    from izbori.history import Archive
    archive = Archive(root)
    best = None
    for rid in archive.round_ids():
        if rid.startswith("L"):
            continue
        mine = [s for s in archive.load(rid).stations if s.municipality_code == code]
        if len(mine) != n:
            continue
        gap = abs((_date(archive.meta(rid).get("date")) - _date(day)).days)
        if best is None or gap < best[0]:
            best = (gap, rid, {s.number: s for s in mine})
    return (best[1], best[2]) if best else (None, {})


def _date(d):
    from datetime import date
    return date.fromisoformat((d or "2000-01-01")[:10])


def build(root, code: str, day: str, name: str, report_url: str, text: str, lists: list[str], log=print) -> dict:
    """Write the draft round of a local election from its report's text; returns a summary."""
    import csv
    import io
    import json
    from pathlib import Path
    k, rows, aside = result_rows(text)
    rid = round_id(code, day)
    rows, aside = corrected(root, rid, rows, aside, log)
    lists = hand_names(root, rid) or lists
    src_round, like = stations_like(root, code, max([r["n"] for r in rows] + [a["n"] for a in aside] + [0]), day)
    out = Path(root) / DRAFTS / rid
    out.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(RESULT_COLUMNS + [f"lista_{i + 1}" for i in range(k)] + ["zapisnik_link", "korekcija_dokument_link"])
    for r in rows:
        s = like.get(str(r["n"]))
        w.writerow([f"{rid}-{r['n']}", r["n"], s.name if s else "", s.municipality if s else name, code,
                    s.district if s else "", s.district_code if s else "", r["registered"], r["voted"], r["ballots"],
                    r["valid"], r["invalid"], ""] + r["v"] + ["", ""])  # the report is not a station's minutes
    (out / "results.csv").write_text("﻿" + buf.getvalue(), encoding="utf-8")
    def contestant(i):
        c = lists[i] if i < len(lists) else f"Изборна листа {i + 1}"
        return c if isinstance(c, dict) else {"name": c}
    meta = {"contest": {}, "contestants": [contestant(i) for i in range(k)],
            "date": day, "kind": "local", "rik_type": 3, "source": "commission",
            "title": f"Локални {day[:4]} - {name}",
            "local": {"municipality": code, "report": report_url, "stations_from": src_round,
                      "aside": [{"n": a["n"], "why": a["why"]} for a in aside],
                      "notes": {str(r["n"]): r["note"] for r in rows if r["note"]}}}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    totals = [sum(r["v"][j] for r in rows) for j in range(k)]
    summary = {"round": rid, "lists": k, "rows": len(rows), "aside": len(aside), "totals": totals,
               "valid": sum(r["valid"] for r in rows), "invalid": sum(r["invalid"] for r in rows),
               "registered": sum(r["registered"] or 0 for r in rows), "stations_from": src_round}
    log(f"{rid}: {summary}")
    for a in aside:
        log(f"  set aside: station {a['n']}: {a['why']}")
    return summary


def list_names(docs: dict, store: dict, code: str, day: str, fetch=None) -> list[tuple[str, str]]:
    """The lists the commission proclaimed for this election: (name as its decision prints it, link), in the
    order of the decisions' links (the order of proclamation is the order on the ballot). A list's name is a
    contestant's, public as RIK's are; nothing else of the decision is kept."""
    out, seen = [], set()
    for u, v in sorted(store["docs"].items()):
        if v["m"] != code or v["k"] != "lists" or v.get("e") not in ("local", None):
            continue
        if v.get("d") and abs((_date(v["d"]) - _date(day)).days) > 60:
            continue
        try:
            text = first_page(u, fetch)
        except Exception:  # noqa: BLE001
            continue
        if "прогла" not in text.lower() and "progla" not in text.lower():
            continue
        m = LIST_NAME.search(text)
        if m:
            nm = re.sub(r"\s+", " ", m.group(1)).strip(" .,")
            if nm.upper() not in seen:
                seen.add(nm.upper())
                out.append((nm, u))
    return out



CORRECTIONS = "local_corrections.csv"  # round, station, registered, voted, ballots, invalid, valid, votes, note
LISTS = "local_lists.csv"  # round, number, rik_name, name, short, source


def corrected(root, rid: str, rows: list[dict], aside: list[dict], log=print) -> tuple[list[dict], list[dict]]:
    """Rows a person read in the report (data/local_corrections.csv): each named cell replaces what OCR read, the
    row must then add up, and it is noted as checked by hand. A station set aside comes back this way."""
    import csv
    from pathlib import Path
    p = Path(root) / CORRECTIONS
    if not p.exists():
        return rows, aside
    by_row = {r["n"]: r for r in rows}
    by_aside = {a["n"]: a for a in aside}
    for c in csv.DictReader(open(p, encoding="utf-8", newline="")):
        if c.get("round") != rid:
            continue
        n = int(c["station"])
        base = dict(by_row.get(n) or (by_aside.get(n) or {}).get("raw") or {})
        if not base:
            log(f"correction for station {n}: no such row")
            continue
        for f in ("registered", "voted", "ballots", "invalid", "valid"):
            if (c.get(f) or "").strip():
                base[f] = int(c[f])
        if (c.get("votes") or "").strip():
            base["v"] = [int(x) for x in c["votes"].split()]
        if None in base["v"] or sum(base["v"]) != base["valid"] or base["ballots"] - base["invalid"] != base["valid"]:
            log(f"correction for station {n} doesn't add up; left as it was")
            continue
        if base.get("voted") is None or base["voted"] < base["ballots"]:
            base["voted"] = base["ballots"]
        note = "checked by hand against the report" + (f" ({c['note']})" if c.get("note") else "")
        by_row[n] = {**{k: base[k] for k in ("registered", "voted", "ballots", "invalid", "valid", "v")}, "n": n,
                     "note": note}
        by_aside.pop(n, None)
    return [by_row[n] for n in sorted(by_row)], [by_aside[n] for n in sorted(by_aside)]


def hand_names(root, rid: str) -> list[dict]:
    """The lists a person entered for this election (data/local_lists.csv: the name as the commission prints it,
    in ordinary case, and short, as RIK's rounds have them), in ballot order."""
    import csv
    from pathlib import Path
    p = Path(root) / LISTS
    if not p.exists():
        return []
    got = sorted((int(r["number"]), r) for r in csv.DictReader(open(p, encoding="utf-8", newline=""))
                 if r.get("round") == rid)
    return [{"name": r["name"], "rik_name": r["rik_name"], "short": r["short"]} for _, r in got]
