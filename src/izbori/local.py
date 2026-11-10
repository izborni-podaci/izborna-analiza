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


REPORT_AFTER = 40  # days after the election in which the commission's report is dated (Sečanj 2025: 21, after a repeat)


def report_candidates(store: dict, code: str, day: str) -> list[str]:
    """The municipality's reports (izveštaj in the link) of a local election, dated from its day to REPORT_AFTER
    days after: the page gives the report's own date, not the election's (Temerin 2024: 6 June), and the first
    page alone may not tell a report from a list's document (Sečanj 2025), so the kind isn't asked; every one is
    read and the one with most stations wins."""
    from datetime import timedelta
    last = (_date(day) + timedelta(days=REPORT_AFTER)).isoformat() if day else "9999"
    return sorted(u for u, v in store["docs"].items() if v["m"] == code and v.get("e") in ("local", None)
                  and (not day or day <= (v.get("d") or "") <= last)
                  and re.search(r"izvest|izvjest", watch.fold(urllib.parse.unquote(u))))


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


HAND = "local_hand.csv"  # round, station, registered, voted, ballots, invalid, valid, votes, source, note


def hand_rows(root, rid: str, log=print) -> tuple[int, list[dict], list[dict], dict[int, str]]:
    """Stations read by eye from their boards' minutes (data/local_hand.csv): (lists, rows, set aside, minutes' link
    by station). A row must add up as a report's does (the lists to the valid votes, the ballots less the invalid
    ones to the valid votes, no more ballots than voters); one that doesn't is set aside, never mended."""
    import csv
    from pathlib import Path
    p = Path(root) / HAND
    rows, aside, links, k = [], [], {}, 0
    if not p.exists():
        return 0, rows, aside, links
    for c in csv.DictReader(open(p, encoding="utf-8", newline="")):
        if c.get("round") != rid:
            continue
        n = int(c["station"])
        r = {f: int(c[f]) for f in ("registered", "voted", "ballots", "invalid", "valid")}
        r.update(n=n, v=[int(x) for x in c["votes"].split()], note=c.get("note") or "")
        k = max(k, len(r["v"]))
        links[n] = c.get("source") or ""
        why = ("the lists don't add up to the valid votes" if sum(r["v"]) != r["valid"] else
               "ballots less invalid aren't the valid votes" if r["ballots"] - r["invalid"] != r["valid"] else
               "more ballots than voters" if r["ballots"] > r["voted"] else "")
        if why:
            aside.append({"n": n, "why": why, "raw": r})
            log(f"station {n}: {why}")
        else:
            rows.append(r)
    return k, sorted(rows, key=lambda r: r["n"]), aside, links


def build(root, code: str, day: str, name: str, report_url: str, text: str | None, lists: list[str], log=print) -> dict:
    """Write the draft round of a local election from its report's text, or, with no text, from the stations read
    by eye from the boards' minutes (data/local_hand.csv); returns a summary."""
    import csv
    import io
    import json
    from pathlib import Path
    rid = round_id(code, day)
    links: dict[int, str] = {}
    if text is None:
        k, rows, aside, links = hand_rows(root, rid, log)
    else:
        k, rows, aside = result_rows(text)
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
                    r["valid"], r["invalid"], ""] + r["v"] + [links.get(r["n"], ""), ""])  # the minutes, when read
    (out / "results.csv").write_text("﻿" + buf.getvalue(), encoding="utf-8")
    def contestant(i):
        c = lists[i] if i < len(lists) else f"Изборна листа {i + 1}"
        return c if isinstance(c, dict) else {"name": c}
    meta = {"contest": {}, "contestants": [contestant(i) for i in range(k)],
            "date": day, "kind": "local", "rik_type": 3, "source": "commission",
            "title": f"Локални {day[:4]} - {name}",
            "local": {"municipality": code, "report": report_url, "stations_from": src_round,
                      **({"from": "minutes"} if text is None else {}),
                      "aside": [{"n": a["n"], "why": a["why"]} for a in aside],
                      "notes": {str(r["n"]): r["note"] for r in rows if r["note"]}}}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if src_round:  # the same stations, so the same census settlements as the round they were named from
        from izbori import settlements
        prev = json.loads((Path(root) / "rounds" / src_round / settlements.STORE).read_text(encoding="utf-8")) \
            if (Path(root) / "rounds" / src_round / settlements.STORE).exists() else {"stations": {}}
        settlements.save_store(out, {k: v for k, v in prev.get("stations", {}).items() if k.startswith(code + "/")})
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


# --- the polling boards: who proposed each member, from the commission's decisions --------------------------------
# A municipal commission appoints each station's board in two decisions: the standing composition (proposed by the
# assembly's groups of councillors) and the extended (one member and a deputy per list, on its proposal: the lists'
# controllers). Pančevo 2024 writes a slot as "1. члан: <person>, <…>, <list>;" and its deputy as "- заменик 1.
# члана: <person>, <…>, <list>;" with no "на предлог", which RIK's reader (boards.parse_decision) doesn't take; so
# each role's own text is matched to a list (role_list), and only the list's number and whether the role
# was filled are kept, as in RIK's rounds (boards.json). Changes, ends and the standing composition are kept as
# links only: whether a list had its member at a station is the appointments' (boards.coverage).
# a member's line, "1. члан:", or a deputy's, "- заменик 1. члана:"; OCR garbles the words ("2. чпан;", "~ замеиик 1.
# чпана:"), so at a line's start a short word in their place, before ":" or ";", still starts the role
ROLE_ENTRY = re.compile(r"(?:^|\n)[\s\-–—~•„\"“«]*(?:(?:заменик|zamenik)\s*\d{1,2}\s*[.,]\s*(?:члана|clana|člana|[^\W\d_]{3,7})"
                        r"\s*[:;]|[^\W\d_]{4,9}[ \t]*\d{1,2}[ \t]*[.,][ \t]*[^\W\d_]{3,7}[ \t]*[:;]"
                        r"|(?P<m>\d{1,2})\s*[.,]\s*(?:члан|clan|član|[^\W\d_]{3,6})\s*[:;])", re.I)
BOARD_WINDOW = 60  # days before the election in which its boards are appointed


def role_list(part: str, contestants: list[dict]) -> int | None:
    """The list a role's text names, from its words after the person (before the first comma): the list with most
    words of its own, words no other list's name has ("Панчево", "против", "насиља" are in three names in
    Pančevo; "борба" only in list 4's, "бирам" in list 3's), clearly ahead of the next, with two of its words in the
    text; or, for a citizens' group named otherwise than its list ("Група грађана „…“"), the round's only list of a
    citizens' group. Otherwise None: not guessed."""
    head, comma, tail = part.partition(",")
    text = tail if comma else part
    words = set(boards._words(text))
    own = [set().union(*(boards.tokens(c.get(k, "")) for k in ("name", "rik_name", "short"))) for c in contestants]
    scores = []
    for n, mine in enumerate(own, start=1):
        others = set().union(*(o for k, o in enumerate(own, start=1) if k != n))
        scores.append((len(words & (mine - others)), len(words & mine), n))
    scores.sort(reverse=True)
    best = scores[0] if scores else (0, 0, None)
    if best[0] >= 1 and (len(scores) == 1 or best[0] > scores[1][0]) and max(best[0], best[1]) >= 2:
        return best[2]
    group = re.compile(r"GRUPA\s+GRADJANA")
    if group.search(watch.fold(text).upper()):
        groups = [n for n, c in enumerate(contestants, start=1)
                  if any(group.search(watch.fold(c.get(k, "")).upper()) for k in ("name", "rik_name"))]
        if len(groups) == 1:
            return groups[0]
    return None


def board_head(text: str) -> str:
    """A decision's title: from "РЕШЕЊЕ" to the station's number (what boards.classify reads)."""
    t = boards._normalize(text)
    start = max(t.find("РЕШЕЊЕ"), t.find("REŠENJE"), t.find("RESENJE"), 0)
    m = boards.STATION.search(t, start)
    return t[start:m.end()] if m and m.end() - start < 900 else t[start:start + 600]


def board_slots(text: str, contestants: list[dict]) -> tuple[list[list], int]:
    """[[ballot number, member filled, deputy filled], …] and how many filled roles named no list clearly."""
    t = boards._normalize(text)
    end = boards.END.search(t)
    body = t[:end.start()] if end else t
    marks = list(ROLE_ENTRY.finditer(body))
    by_list: dict[int, list[bool]] = {}
    unmatched = 0
    for k, m in enumerate(marks):
        part = body[m.end(): marks[k + 1].start() if k + 1 < len(marks) else len(body)]
        if not boards._filled(part):
            continue
        number = role_list(" ".join(part.split()), contestants)
        if number is None:
            unmatched += 1
            continue
        roles = by_list.setdefault(number, [False, False])
        roles[0 if m.group("m") else 1] = True
    return [[n, m, d] for n, (m, d) in sorted(by_list.items())], unmatched


def role_shape(text: str, contestants: list[dict]) -> list[str]:
    """Each extended role's text with every word masked but the lists' own words after its first comma (the person
    comes first), and the list it was matched to: to see why a role names no list, without a name in a log."""
    own = set().union(*(boards.tokens(c.get(k, "")) for c in contestants for k in ("name", "rik_name", "short")))
    t = boards._normalize(text)
    end = boards.END.search(t)
    body = t[:end.start()] if end else t
    marks = list(ROLE_ENTRY.finditer(body))
    out = []
    for k, m in enumerate(marks):
        part = " ".join(body[m.end(): marks[k + 1].start() if k + 1 < len(marks) else len(body)].split())
        head, _, tail = part.partition(",")
        masked = LETTERS_WORD.sub(lambda w: w.group(0) if boards.tokens(w.group(0)) & own else "xxx", tail)
        out.append(f"{shape(m.group(0).strip(), 80)} xxx,{masked} -> {role_list(part, contestants)}")
    return out


def read_board(text: str, url: str, day: str | None, contestants: list[dict], numbers: set[str], code: str) -> dict | None:
    """What boards.json keeps of one decision of a local commission, or None when it isn't one on a station's board."""
    t = boards._normalize(text)
    up = t.upper()
    if "ОДБОР" not in up and "ODBOR" not in up:
        return None
    head = board_head(text)
    if "ЗАПИСНИК" in head.upper() or "ZAPISNIK" in head.upper():
        return None
    m = boards.STATION.search(t)
    if not m or m.group(1).lstrip("0") not in numbers:
        return None
    kind, repeat = boards.classify(head, "")
    if kind == "other":
        return None
    entry = {"s": f"{code}/{m.group(1).lstrip('0')}", "k": kind, "r": repeat, "t": day or "", "u": url, "v": boards.PARSER}
    if kind == "extended":
        decision = boards.parse_decision(text)
        slots, unmatched = board_slots(text, contestants)
        if not slots and decision.slots:  # RIK's layout, "на предлог …"
            slots = [[boards.slot_list(s, contestants), s.member, s.deputy] for s in decision.slots]
            unmatched = sum(1 for s in slots if s[0] is None)
        entry.update(slots=slots, unmatched=unmatched, addr=decision.address, unparsed=not slots)
    return entry


def board_candidates(store: dict, code: str, day: str) -> list[str]:
    """The municipality's documents dated in the weeks before the election (a board decision may be filed as a
    list's document: it names the lists), not its minutes or results."""
    from datetime import timedelta
    first = (_date(day) - timedelta(days=BOARD_WINDOW)).isoformat()
    return sorted(u for u, v in store["docs"].items() if v["m"] == code and v.get("e") in ("local", None)
                  and v.get("d") and first <= v["d"] <= day and v["k"] not in ("minutes", "results"))


def _board_one(args: tuple) -> tuple[str, dict | None, str | None]:
    url, day, contestants, numbers, code, diagnose = (*args, False)[:6]
    try:
        text = text_of(download(url), url, pages=3)
        got = read_board(text, url, day, contestants, numbers, code)
        if got and diagnose and got["k"] == "extended":
            got["_roles"] = role_shape(text, contestants)
        return url, got, None
    except Exception as e:  # noqa: BLE001 - a document down: left out of this run
        return url, None, type(e).__name__


def read_boards(root, rid: str, log=print, workers: int = 4, one=_board_one, only: str = "") -> dict:
    """Read a local round's board decisions into data/rounds/<rid>/boards.json; returns a summary (no names).

    With `only`, just the documents whose link holds it (or one of its parts between "|"), each extended one's roles logged masked (role_shape);
    nothing is written."""
    import csv
    import json
    from collections import Counter
    from concurrent.futures import ProcessPoolExecutor
    from pathlib import Path
    rdir = Path(root) / "rounds" / rid
    meta = json.loads((rdir / "meta.json").read_text(encoding="utf-8"))
    code, day, contestants = meta["local"]["municipality"], meta["date"], meta["contestants"]
    with open(rdir / "results.csv", encoding="utf-8-sig", newline="") as f:
        numbers = {r["bm_broj"].strip() for r in csv.DictReader(f)}
    store = load_store(root)
    days = {u: store["docs"][u].get("d") for u in board_candidates(store, code, day)
            if not only or any(o and o in urllib.parse.unquote(u) for o in only.split("|"))}
    log(f"{rid}: {len(days)} documents of the weeks before the election to look at")
    items = [(u, d, contestants, numbers, code) + ((True,) if only else ()) for u, d in days.items()]
    out, failed = {}, []
    if workers > 1:
        with ProcessPoolExecutor(workers) as pool:
            results = list(pool.map(one, items))
    else:
        results = [one(i) for i in items]
    for url, got, err in results:
        if err:
            failed.append(err)
        elif got:
            for line in got.pop("_roles", []):
                log(f"{urllib.parse.unquote(url).rsplit('/', 1)[-1][:40]}: {line}")
            out[url] = got
    if not only:
        boards.save_store(rdir, {"complete": not failed, "indexed": len(days), "read": now_day(), "source": "commission",
                                 "docs": out})
    ext = [d for d in out.values() if d["k"] == "extended"]
    cov = boards.coverage({"docs": out})
    summary = {"decisions": len(out), "kinds": dict(Counter(d["k"] for d in out.values())),
               "extended_unread": sum(1 for d in ext if d.get("unparsed")),
               "roles_unmatched": sum(d.get("unmatched", 0) for d in ext),
               "stations": len(numbers), "stations_read": sum(1 for c in cov.values() if c.get("lists") is not None),
               "per_list": {str(n): sum(1 for c in cov.values() if (c.get("lists") or {}).get(str(n), {}).get("member"))
                            for n in range(1, len(contestants) + 1)},
               "failed": dict(Counter(failed))}
    log(json.dumps(summary, ensure_ascii=False))
    return summary


def now_day() -> str:
    from datetime import date
    return date.today().isoformat()


# --- the boards' minutes, where a commission published no results by station -------------------------------------
# Temerin 2024 and Sečanj 2025 published only the municipality's totals; each station's results are in its board's
# minutes, filled in by hand, which OCR can't read. So the minutes' results section alone (from "РЕЗУЛТАТИ" to the
# next part of the form: the board, its members' signatures, remarks) is cut out as an image to be read by eye, never
# the members' part; the images go to a temporary branch, deleted once read. What is read goes into
# data/local_hand.csv and must add up, row by row and to the commission's totals.
RESULTS_HEAD = re.compile(r"РЕЗУЛТАТИ|REZULTATI")
REGISTERED = re.compile(r"УПИСАН(?:И|ИХ)\b|UPISAN(?:I|IH)\b")  # the row with the registered voters, in an earlier part of the form
CROP_END = re.compile(r"\b(?:ЧЛАН|ЗАМЕНИК|ПРЕДСЕДНИК|ПРИМЕДБ\w*|ПОДАЦИ|ПОТПИС\w*|ЧИЊЕНИЦ\w*|НАПОМЕН\w*|БИРАЧКИ\s+ОДБОР)\b"
                      r"|^\W*1\s*[.,]\s*Број\s+бирачког\s+места|^\W*\d+\s*[.,]\s*Датум")
CROP_DPI = 200


def page_lines(png) -> tuple[list[tuple[str, int, int, int]], int, int]:
    """A page image's lines as Tesseract finds them: (text, top, bottom, centre x) in pixels, and the page's width
    and height."""
    import os
    import subprocess
    r = subprocess.run(["tesseract", str(png), "-", "-l", "srp+srp_latn", "tsv"], capture_output=True, text=True,
                       env={**os.environ, "OMP_THREAD_LIMIT": "1"})
    lines: dict[tuple, list] = {}
    width = height = 0
    for row in r.stdout.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12:
            continue
        level, left, top, w, h = int(f[0]), int(f[6]), int(f[7]), int(f[8]), int(f[9])
        if level == 1:
            width, height = w, h
        if level == 5 and f[11].strip():
            # a line Tesseract runs across both pages of a spread is split at the fold (Temerin's BM 23)
            half = width > height and left + w / 2 >= width / 2
            cur = lines.setdefault((f[1], f[2], f[3], f[4], half), [[], top, top + h, left, left + w])
            cur[0].append(f[11])
            cur[1], cur[2] = min(cur[1], top), max(cur[2], top + h)
            cur[3], cur[4] = min(cur[3], left), max(cur[4], left + w)
    return sorted(((" ".join(t), a, b, (x0 + x1) // 2) for t, a, b, x0, x1 in lines.values()),
                  key=lambda x: x[1]), width, height


def columns(width: int, height: int) -> list[tuple[int, int]]:
    """A scan of two pages side by side (wider than tall) is read as two columns, left first."""
    return [(0, width // 2), (width // 2, width)] if width > height else [(0, width)]


def result_regions(pages: list[tuple[list, int, int]]) -> list[tuple[int, int, int, int, int]]:
    """Where the results section is: [(page index, top, bottom, x0, x1)], from its heading to the next part of the
    form, in the heading's column (a spread of two pages is two columns), onto the next column when it runs over;
    nothing when there is no heading."""
    cols = [(i, x0, x1, h) for i, (lines, h, w) in enumerate(pages) for x0, x1 in columns(w, h)]

    def col_lines(c):
        i, x0, x1, _ = c
        return [ln for ln in pages[i][0] if x0 <= ln[3] < x1]
    registered = []  # the registered voters' row: a band of the form around it, its own line only
    for c in cols:
        hit = next((ln for ln in col_lines(c) if REGISTERED.search(ln[0])), None)
        if hit:
            registered = [(c[0], max(0, hit[1] - 60), min(c[3], hit[2] + 140), c[1], c[2])]
            break
    return registered + _results(cols, col_lines)


def _results(cols, col_lines) -> list[tuple[int, int, int, int, int]]:
    for k, c in enumerate(cols):
        lines = col_lines(c)
        start = next((j for j, ln in enumerate(lines) if RESULTS_HEAD.search(ln[0]) and len(ln[0].split()) <= 6), None)
        if start is None:
            continue
        i, x0, x1, h = c
        top = max(0, lines[start][1] - 15)
        end = next((ln[1] for ln in lines[start + 1:] if CROP_END.search(ln[0])), None)
        if end is not None:
            return [(i, top, end - 5, x0, x1)]
        out = [(i, top, h, x0, x1)]
        if k + 1 < len(cols):
            n = cols[k + 1]
            stop = next((ln[1] for ln in col_lines(n) if CROP_END.search(ln[0])), n[3] // 2)
            if stop > 20:
                out.append((n[0], 0, stop - 5, n[1], n[2]))
        return out
    return []


def crop_results(pdf: bytes, out_dir, stem: str, max_pages: int = 4) -> list:
    """The minutes' results section as PNG images in out_dir (stem-p<page>-<n>.png); [] when it isn't found."""
    import subprocess
    import tempfile
    from pathlib import Path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "doc.pdf"
        path.write_bytes(pdf)
        pages = []
        for p in range(1, max_pages + 1):
            prefix = Path(tmp) / f"p{p}"
            r = subprocess.run(["pdftoppm", "-r", str(CROP_DPI), "-gray", "-png", "-f", str(p), "-l", str(p),
                                str(path), str(prefix)], capture_output=True)
            images = sorted(Path(tmp).glob(f"p{p}*.png"))
            if r.returncode != 0 or not images:
                break
            lines, w, h = page_lines(images[0])
            pages.append((lines, h, w))
            images[0].unlink()
        for n, (i, top, bottom, x0, x1) in enumerate(result_regions(pages), 1):
            target = out_dir / f"{stem}-p{i + 1}-{n}"
            subprocess.run(["pdftoppm", "-r", str(CROP_DPI), "-gray", "-png", "-singlefile", "-f", str(i + 1),
                            "-l", str(i + 1), "-x", str(x0), "-y", str(top), "-W", str(x1 - x0), "-H",
                            str(max(1, bottom - top)), str(path), str(target)], capture_output=True)
            if Path(f"{target}.png").exists():
                made.append(Path(f"{target}.png"))
    return made


def safe_stem(url: str) -> str:
    name = urllib.parse.unquote(url).rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return re.sub(r"[^a-z0-9]+", "-", watch.fold(name)).strip("-")[:80]


def run_crops(root, code: str, path_has: str, out_dir, log=print, fetch=None) -> int:
    """Cut the results section out of a municipality's boards' minutes (links holding one of path_has's parts
    between "|"); returns how many minutes gave an image."""
    store = load_store(root)
    parts = [p for p in path_has.split("|") if p]
    todo = sorted(u for u, v in store["docs"].items() if v["m"] == code and v["k"] == "minutes"
                  and (not parts or any(p in urllib.parse.unquote(u) for p in parts)))
    log(f"{code}: {len(todo)} minutes")
    done = 0
    for u in todo:
        try:
            made = crop_results((fetch or download)(u), out_dir, f"{code}-{safe_stem(u)}")
        except Exception as e:  # noqa: BLE001 - one document down must not stop the rest
            log(f"{safe_stem(u)}: {type(e).__name__}")
            continue
        log(f"{safe_stem(u)}: {len(made)} image(s)")
        done += bool(made)
    return done
