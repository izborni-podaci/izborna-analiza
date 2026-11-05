"""Command line: izbori rounds | fetch | import | update | documents | boards | observers | site | targets | check."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from izbori import feed, mail, schedule
from izbori.config import SITE_URL
from izbori.history import Archive, now_iso
from izbori.i18n import BELGRADE, check_name, parse_time
from izbori.notes import write_template
from izbori.report import analyze, record_new_flags
from izbori.rik import Client, RikError, Summary, guess_kind
from izbori.translit import latin

WATCH_REFRESH = timedelta(minutes=15)  # while watching, re-download at least this often
# How often RIK is asked follows the election calendar (schedule.py). A round this long after its election day,
# and not counting, no longer changes, so it is looked at once a week; every other round is re-downloaded once a
# day even if RIK's progress looks unchanged.
SETTLED_AFTER = timedelta(days=30)


def log(msg: str) -> None:
    print(f"[{datetime.now(UTC):%H:%M:%S}] {msg}", flush=True)


# --- shared steps ---------------------------------------------------------------------------

def ensure_meta(archive: Archive, rid: str, info: dict, summ: Summary | None) -> dict:
    meta = archive.meta(rid)
    if not meta:
        meta = {"kind": info.get("kind", "unknown"), "rik_type": info.get("type"),
                "title": (summ.title if summ else "") or info.get("name", rid), "contest": {}, "contestants": []}
    if summ and summ.contestants and not meta.get("contestants"):
        meta["contestants"] = [{"name": name} for _, name in summ.contestants]
    if summ and summ.title and not meta.get("title"):
        meta["title"] = summ.title
    archive.save_meta(rid, meta)
    return meta


def after_change(archive: Archive, rid: str, when: str, notes_dir: Path, notify: bool, announce: bool = True) -> int:
    """Record new flags, add a feed entry and queue an email. Returns the number of new flags."""
    a = analyze(archive, rid, notes_dir)
    new = record_new_flags(archive, a, when)
    if new and announce:
        entry = feed.make_entry(a, new, when)
        feed.add_entry(archive.root, entry)
        if notify:
            mail.queue(archive.root, entry=entry)
    write_template(notes_dir, rid)
    return len(new)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def commit(paths: list[str], message: str) -> bool:
    git("add", "-A", *paths)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return False
    git("commit", "-m", message)
    return True


def push() -> bool:
    for _ in range(3):
        if git("push", check=False).returncode == 0:
            return True
        git("pull", "--rebase", check=False)
    log("push failed")
    return False


def dispatch_pages() -> None:
    r = subprocess.run(["gh", "workflow", "run", "pages.yml"], capture_output=True, text=True)
    if r.returncode != 0:
        log(f"could not start the pages workflow: {r.stderr.strip()}")


def heartbeat(data: Path) -> None:
    """GitHub turns off schedules in repositories without activity for 60 days."""
    r = git("log", "-1", "--format=%ct", check=False)
    last = int(r.stdout.strip() or 0)
    if time.time() - last > 30 * 86400:
        (data / "heartbeat.txt").write_text(now_iso() + "\n", encoding="utf-8")


# --- commands -------------------------------------------------------------------------------

def cmd_rounds(args) -> int:
    archive = Archive(args.data)
    found = Client().all_rounds()
    archived = set(archive.round_ids())
    for rid, info in sorted(found.items(), key=lambda kv: (kv[1]["type"], kv[0])):
        mark = "archived" if rid in archived else ""
        print(f"{rid:>8}  type {info['type']:<2} {info['kind']:<14} {latin(info['name'])}  {mark}")
    return 0


def fetch_round(client: Client, archive: Archive, rid: str, info: dict, notes_dir: Path, notify: bool,
                force: bool = False, last_download: dict | None = None) -> tuple[bool, Summary | None, bool]:
    """Fetch one round if RIK's progress changed. Returns (archived something new, summary, count finished)."""
    summ = client.summary(info["type"], rid)
    state = archive.state(rid)
    signature = [summ.counted, summ.total]
    finished = bool(state.get("counting")) and not summ.counting and summ.counted is not None
    stale = (last_download is not None and summ.counting
             and datetime.now(UTC) - last_download.get(rid, datetime.min.replace(tzinfo=UTC)) >= WATCH_REFRESH)
    unchanged = state.get("signature") == signature and archive.latest_raw(rid) is not None
    if not summ.allowed or (unchanged and not force and not stale):
        if state.get("counting") != summ.counting and summ.allowed:
            archive.save_state(rid, {"signature": state.get("signature"), "counting": summ.counting})
        return False, summ, finished
    raw, filename = client.export(rid)
    if last_download is not None:
        last_download[rid] = datetime.now(UTC)
    ensure_meta(archive, rid, info, summ)
    when = now_iso()
    result = archive.add_snapshot(rid, raw, fetched=when, rik_time=summ.rik_time, total=summ.total,
                                  filename=filename)
    archive.save_state(rid, {"signature": signature, "counting": summ.counting})
    if result:
        n = after_change(archive, rid, when, notes_dir, notify)
        log(f"{rid}: archived ({summ.counted}/{summ.total} counted, {len(result.changes)} changes, {n} new flags)")
    return result is not None, summ, finished


def cmd_fetch(args) -> int:
    archive = Archive(args.data)
    client = Client()
    known = archive.known_rounds()
    info = known.get(args.round) or ({"type": args.type, "name": "", "kind": guess_kind(args.type, "")}
                                     if args.type else None)
    if info is None:
        info = client.all_rounds().get(args.round)
    if info is None:
        print(f"RIK doesn't list round {args.round}; pass --type", file=sys.stderr)
        return 1
    changed, summ, _ = fetch_round(client, archive, args.round, info, args.notes, notify=False, force=True)
    print("archived a new version" if changed else "nothing new")
    return 0


def _time_from_filename(name: str) -> str | None:
    m = re.search(r"(\d\d)_(\d\d)_(\d\d)_(\d\d)\.(\d\d)\.(\d{4})", name) or \
        re.search(r"(\d\d):(\d\d):(\d\d)_(\d\d)\.(\d\d)\.(\d{4})", name)
    if not m:
        return None
    hh, mm, ss, dd, mo, yy = (int(x) for x in m.groups())
    local = datetime(yy, mo, dd, hh, mm, ss, tzinfo=BELGRADE)
    return local.astimezone(UTC).isoformat()


def cmd_import(args) -> int:
    archive = Archive(args.data)
    raw = Path(args.file).read_bytes()
    meta = archive.meta(args.round)
    if not meta:
        contestants = json.loads(Path(args.contestants).read_text(encoding="utf-8")) if args.contestants else []
        meta = {"kind": args.kind, "rik_type": args.type, "title": args.title or args.round, "contest": {},
                "contestants": [{"name": c.get("name", ""), "short": c.get("short", ""),
                                 "minority": bool(c.get("minority"))} for c in contestants]}
        archive.save_meta(args.round, meta)
    when = args.fetched or _time_from_filename(Path(args.file).name) or now_iso()
    rik_time = args.rik_time
    if rik_time is None:
        local = parse_time(when)
        rik_time = local.astimezone(BELGRADE).strftime("%d.%m.%Y %H:%M:%S") if local else None
    result = archive.add_snapshot(args.round, raw, fetched=when, rik_time=rik_time,
                                  filename=Path(args.file).name.split("-", 1)[-1])
    if result is None:
        print("identical to the latest archived file; nothing added")
        return 0
    n = after_change(archive, args.round, when, args.notes, notify=False)
    print(f"archived: {len(result.new_stations)} stations with first results, {len(result.changes)} changes, "
          f"{n} new flags")
    return 0


def settled(archive: Archive, rid: str, now: datetime) -> bool:
    """A round long past its election day and not counting: its results no longer change."""
    date = archive.meta(rid).get("date")
    if not date or archive.state(rid).get("counting"):
        return False
    return now.date() - datetime.fromisoformat(date[:10]).date() > SETTLED_AFTER


def hours(d: timedelta | None) -> str:
    return "never" if d is None else f"{d.total_seconds() / 3600:.1f} h"


def dispatch_update() -> None:
    """Start the update workflow again (it waits for this run to end): GitHub's hourly schedule skips many runs,
    so a count still open isn't left to it."""
    r = subprocess.run(["gh", "workflow", "run", "update.yml"], capture_output=True, text=True)
    if r.returncode != 0:
        log(f"could not start the update workflow again: {r.stderr.strip()}")


def cmd_update(args) -> int:
    archive = Archive(args.data)
    now = datetime.now(UTC)
    period, why = schedule.every(archive, now)
    if not args.always and not schedule.due(archive.root, "rik", now, period):
        log(f"RIK is asked every {hours(period)} now ({why}); last asked {hours(schedule.since(archive.root, 'rik', now))}"
            " ago")
        if args.commit:
            heartbeat(Path(args.data))
            if commit([str(args.data)], f"Heartbeat ({now_iso()})") and args.push:
                push()
        return 0
    log(f"asking RIK ({why})")
    weekly = schedule.due(archive.root, "settled", now, timedelta(days=7))  # one look a week at settled rounds
    refresh = schedule.due(archive.root, "refresh", now, timedelta(days=1))  # one re-download a day
    client = Client()
    deadline = time.monotonic() + args.max_minutes * 60
    last_download: dict = {}
    first = True
    while True:
        changed: list[str] = []
        counting = False
        try:
            found = client.all_rounds()
        except RikError as e:
            log(f"RIK unreachable: {e}")
            found = {}
        if found:
            known = archive.known_rounds()
            merged = {**known, **found}
            if merged != known:
                archive.save_known_rounds(merged)
        force = first and refresh
        for rid, info in sorted(found.items()):
            old = settled(archive, rid, now)
            if old and not (first and weekly):
                continue
            try:
                did, summ, finished = fetch_round(client, archive, rid, info, args.notes, args.notify,
                                                  force=force and not old,
                                                  last_download=last_download if args.watch else None)
            except RikError as e:
                log(f"{rid}: {e}")
                continue
            if did:
                changed.append(rid)
            if finished and args.notify:
                mail.queue(archive.root, final_round=rid)
            when = parse_time(summ.rik_time) if summ else None
            recent = when is None or datetime.now(UTC) - when < timedelta(days=7)
            if summ and summ.counting and recent and summ.allowed:
                counting = True
        if first and found:  # RIK answered: the next look is a whole period away
            schedule.record(archive.root, now, "rik", *(["settled"] if weekly else []), *(["refresh"] if refresh else []))
        if args.notify:
            mail.maybe_send(archive.root, archive, args.site_url, datetime.now(UTC))
        if args.commit:
            if first:
                heartbeat(Path(args.data))
            label = ", ".join(changed) if changed else "state"
            if commit([str(args.data), str(args.notes)], f"Data: {label} ({now_iso()})"):
                if args.push and push() and args.dispatch_pages and changed:
                    dispatch_pages()
        first = False
        if not args.watch or not counting:
            break
        if time.monotonic() + args.every > deadline:
            log("watch time is up; a new run continues")
            if args.rerun:
                dispatch_update()
            break
        time.sleep(args.every)
    return 0


BOARDS_AFTER = timedelta(days=14)  # the daily run stops reading decisions on boards this long after election day
BOARDS_CHECKPOINT = 2 * 3600  # seconds between commits while one long run reads decisions


def cmd_boards(args) -> int:
    """Read which lists appointed members to the extended polling boards (controllers).

    In one go, or in three steps that let several jobs read at once: --plan FILE indexes the register and lists
    what to read; --read FILE --shard I/N reads one part of that list into --out; --merge FILE PART... keeps it
    all in the round's store."""
    import os
    from izbori import boards
    archive = Archive(args.data)
    workers = args.workers or os.cpu_count() or 2
    if args.read:  # one part of a plan: no RIK register, no store, only the decisions themselves
        planned = json.loads(Path(args.read).read_text(encoding="utf-8"))
        i, n = (int(x) for x in args.shard.split("/"))
        todo = [d for k, d in enumerate(planned["todo"]) if k % n == i][: args.limit]
        log(f"{planned['round']}: part {i + 1} of {n}, {len(todo)} decisions to read")
        got = boards.read(todo, planned["contestants"], Client().base, workers, args.budget_minutes * 60, log,
                          args.diagnose)
        Path(args.out).write_text(json.dumps(got, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return 0
    if args.merge:
        planned = json.loads(Path(args.merge).read_text(encoding="utf-8"))
        rid = planned["round"]
        store = boards.load_store(archive.dir(rid))
        boards.apply_index(store, planned)
        read = failed = left = 0
        parts = [json.loads(Path(f).read_text(encoding="utf-8")) for f in args.parts]
        for part in parts:
            boards.apply_results(store, part["results"])
            read, failed, left = read + len(part["results"]), failed + len(part["failed"]), left + part["left"]
        done = {d for part in parts for d in part["results"]}
        store["complete"] = not failed and not left and all(d["id"] in done for d in planned["todo"])
        boards.save_store(archive.dir(rid), store)
        log(f"{rid}: {len(parts)} parts merged, {read} decisions read, failed {failed}, left {left}")
        show_boards(archive, rid, planned["contestants"], args.show)
        if args.commit and commit([str(args.data)], f"Boards: {rid}, {read} decisions read ({now_iso()})"):
            if args.push and push() and args.dispatch_pages:
                dispatch_pages()
        return 0

    client = Client()
    known = archive.known_rounds()
    if not known:
        known = client.all_rounds()
        archive.save_known_rounds(known)
    rid = args.round or max(known, key=lambda r: int(r) if r.isdigit() else 0)
    info = known.get(rid) or {"type": args.type or 2, "name": "", "kind": "unknown"}
    meta = archive.meta(rid)
    date = meta.get("date")
    if not args.round and date and datetime.now(UTC).date() - datetime.fromisoformat(date[:10]).date() > BOARDS_AFTER:
        log(f"{rid}: election day {date} is past; boards are appointed before it, so nothing is read")
        return 0
    if not meta.get("contestants"):
        try:
            meta = ensure_meta(archive, rid, info, client.summary(info["type"], rid))
        except RikError as e:
            log(f"{rid}: no contestants yet ({e})")
    contestants = meta.get("contestants") or []
    if not contestants:
        log(f"{rid}: contestants unknown, nothing to match against")
        return 1
    source = rid if archive.latest_raw(rid) is not None else (archive.round_ids() or [None])[-1]
    if source is None:
        log("no archived results to map municipalities from")
        return 1
    stations = {boards.municipality_key(s.municipality): s.municipality_code for s in archive.load(source).stations}
    archive.dir(rid).mkdir(parents=True, exist_ok=True)
    if args.plan:
        planned = boards.plan(archive.dir(rid), rid, int(info["type"]), stations, client, log, args.retry_unparsed)
        planned["contestants"] = contestants
        Path(args.plan).write_text(json.dumps(planned, ensure_ascii=False), encoding="utf-8")
        return 0
    last_commit = [time.monotonic()]

    def checkpoint():  # a long run keeps its work now and then, rather than in many small commits
        if args.commit and time.monotonic() - last_commit[0] > BOARDS_CHECKPOINT:
            if commit([str(args.data)], f"Boards: {rid} ({now_iso()})") and args.push:
                push()
            last_commit[0] = time.monotonic()

    result = boards.run(archive.dir(rid), rid, int(info["type"]), contestants, stations, client,
                        workers=workers, budget_seconds=args.budget_minutes * 60, limit=args.limit, log=log,
                        checkpoint=checkpoint, diagnose=args.diagnose, retry_unparsed=args.retry_unparsed)
    show_boards(archive, rid, contestants, args.show)
    if args.commit and commit([str(args.data)], f"Boards: {rid}, {result['read']} decisions read ({now_iso()})"):
        if args.push and push() and args.dispatch_pages:
            dispatch_pages()
    return 0


def show_boards(archive: Archive, rid: str, contestants: list, n: int) -> None:
    """Log the first n stations' lists with a member, and their addresses (no names)."""
    from izbori import boards
    if not n:
        return
    cov = boards.coverage(boards.load_store(archive.dir(rid)))
    for key in sorted(cov)[:n]:
        c = cov[key]
        if c["lists"] is None:
            log(f"{key}: decision not readable")
            continue
        members = sorted(int(x) for x, v in c["lists"].items() if v["member"])
        log(f"{key}: lists with a member {members} of {len(contestants)}; unmatched {c['unmatched']}; "
            f"address: {latin(c['address'])}")
    log(f"stations with a decision read: {len(cov)}")


def cmd_geo(args) -> int:
    """Municipal boundaries from OpenStreetMap for the map on the Explore page (data/geo/municipalities.json)."""
    from izbori import geo
    archive = Archive(args.data)
    out = Path(args.out) if args.out else Path(args.data) / "geo" / "municipalities.json"
    data = geo.fetch()
    feats = geo.features(data)
    geo.write(out, feats, now_iso()[:10])
    have = {f["properties"]["code"] for f in feats}
    names: dict[str, str] = {}
    for rid in archive.round_ids():
        for s in archive.load(rid).stations:
            names.setdefault(s.municipality_code, s.municipality)
    missing = sorted(code for code in names if code not in have)
    log(f"{len(feats)} boundaries; {len(names) - len(missing)} of the archive's {len(names)} municipalities have one")
    for code in missing:
        log(f"  no boundary: {code} {latin(names[code])}")
    if args.commit and commit([str(out)], "Data: municipal boundaries from OpenStreetMap"):
        if args.push and push() and args.dispatch_pages:
            dispatch_pages()
    return 0


def cmd_documents(args) -> int:
    """Read RIK's register of minutes: every document published for each polling station (minutes, observers'
    records, remarks, corrections, rulings). Keeps labels, links and upload times; no names."""
    from izbori import boards, commission, documents
    archive = Archive(args.data)
    client = Client()
    known = archive.known_rounds()
    now = datetime.now(UTC)
    recent = (now - timedelta(days=args.recent_days)).date().isoformat()

    def due(rid: str) -> bool:
        """Rounds not read yet; daily for two weeks after election day, then on Mondays until --recent-days."""
        date = archive.meta(rid).get("date")
        if not documents.path(archive.dir(rid)).exists() or not date:
            return True
        age = (now.date() - datetime.fromisoformat(date[:10]).date()).days
        return age <= 14 or (date >= recent and now.weekday() == 0)

    ids = [args.round] if args.round else [r for r in archive.round_ids() if args.all or due(r)]
    # the commissions' documents of a round never read (once each, also for older rounds)
    missing = [r for r in archive.round_ids() if r not in ids and not commission.path(archive.dir(r)).exists()]
    if not ids and not missing:
        log("no round due: nothing is asked of RIK")
    changed = []
    # The register names municipalities as RIK does today; an older results file may not ("Ниш-Медијана" for
    # "Градска општина Медијана"). Codes don't change, so names from every archived election map to them.
    loaded = {r: archive.load(r) for r in archive.round_ids()}
    every = {}
    for other in loaded.values():
        for s in other.stations:
            every.setdefault(boards.municipality_key(s.municipality), s.municipality_code)
    for rid in ids + missing:
        rik_type = int(archive.meta(rid).get("rik_type") or (known.get(rid) or {}).get("type") or 0)
        if not rik_type:
            log(f"{rid}: RIK's election type unknown, skipped")
            continue
        rnd = loaded.get(rid) or archive.load(rid)
        codes = {**every, **{boards.municipality_key(s.municipality): s.municipality_code for s in rnd.stations}}
        try:
            if commission.update(client, archive.dir(rid), rid, rik_type, codes, log=log):
                changed.append(rid)
        except RikError as e:
            log(f"{rid}: commission documents not reachable ({e})")
        if rid in missing:
            continue
        before = documents.load(archive.dir(rid))
        try:
            counts = documents.counts(client, rid, rik_type)
            if before and not (args.round or args.all) and counts == documents.saved_counts(archive.dir(rid)):
                log(f"{rid}: register unchanged since the last reading ({sum(counts.values())} documents watched)")
                continue
            records = documents.fetch(client, rid, rik_type, threads=args.threads, log=log)
        except RikError as e:
            log(f"{rid}: register not reachable ({e})")
            continue
        data = {**documents.store(records, codes), "counts": counts}
        kinds = Counter(documents.classify(data["labels"][i])[0] for rows in data["stations"].values() for i, _, _ in rows)
        log(f"{rid}: {len(records)} register records, {len(data['stations'])} stations, documents {dict(kinds)}")
        if data["unmatched"]:
            log(f"{rid}: {len(data['unmatched'])} records with an unknown municipality, e.g. "
                f"{sorted({m for m, _ in data['unmatched']})[:5]}")
        if len(data["stations"]) < 0.9 * len(before):  # a partial answer never replaces a fuller one
            log(f"{rid}: only {len(data['stations'])} stations now, {len(before)} before; kept the earlier file")
            continue
        if documents.save(archive.dir(rid), data):
            # new flags go to the feed only for a recent round read before; filling in older ones stays quiet
            announce = bool(before) and (archive.meta(rid).get("date") or "9999") >= recent
            n = after_change(archive, rid, now_iso(), args.notes, notify=args.notify and announce, announce=announce)
            log(f"{rid}: documents changed, {n} new flags" + ("" if announce else " (not announced)"))
            if rid not in changed:
                changed.append(rid)
    if args.commit and changed and commit([str(args.data), str(args.notes)],
                                          f"Documents: {', '.join(changed)} ({now_iso()})"):
        if args.push and push() and args.dispatch_pages:
            dispatch_pages()
    return 0


def cmd_observers(args) -> int:
    """Observers' records (RG-11): score each once with OCR (no text kept), or write the list to review."""
    import os
    from izbori import observers
    from izbori.report import station_documents
    archive = Archive(args.data)
    rids = archive.round_ids()
    if not rids:
        return 0
    rid = args.round or rids[-1]
    if args.merge:
        today = datetime.now(BELGRADE).date().isoformat()
        added, changed = observers.merge_reviews(archive.dir(rid), Path(args.merge), today)
        print(f"{rid}: {added} reviews added, {changed} changed in {archive.dir(rid) / observers.REVIEWS}")
        return 0
    if args.review:
        a = analyze(archive, rid, args.notes)
        rows = observers.review_rows(a, observers.load_scores(archive.dir(rid)).get("docs", {}))
        observers.write_review(rows, rid, Path(args.out), Path(args.html) if args.html else None)
        template = observers.write_template(archive.dir(rid))
        print(f"{len(rows)} observers' records to read → {args.out}" + (f" and {args.html}" if args.html else ""))
        print(f"Fill in remarks (yes/no), a short summary that names no one, and the date in {args.out}, then "
              f"`izbori observers --merge {args.out}` copies those rows into {template}.")
        return 0
    date = archive.meta(rid).get("date")
    if not args.round and date and (datetime.now(UTC).date() - datetime.fromisoformat(date[:10]).date()).days > 60:
        log(f"{rid}: election day {date} is long past; pass --round to read its observers' records")
        return 0
    docs = station_documents(archive, archive.load(rid))
    records = [(key, d.url) for key, ds in sorted(docs.items()) for d in ds if d.kind == "observers"
               and (not args.station or key in args.station)]
    result = observers.run(archive.dir(rid), records, Client(), workers=args.workers or os.cpu_count() or 2,
                           budget_seconds=args.budget_minutes * 60, limit=args.limit, log=log, diagnose=args.diagnose,
                           layout=args.layout, again=bool(args.station))
    if args.commit and commit([str(args.data)], f"Observers: {rid}, {result['read']} records scored ({now_iso()})"):
        if args.push:
            push()
    return 0


def cmd_import_app(args) -> int:
    """Rebuild a finished round's results from RIK's results app, station by station, and archive it."""
    from izbori import appdata, boards
    archive = Archive(args.data)
    client = Client()
    known = archive.known_rounds() or client.all_rounds()
    info = known.get(args.round) or {"type": args.type, "kind": guess_kind(args.type or 0, ""), "name": ""}
    rik_type = int(args.type or info["type"])
    ids = [r for r in archive.round_ids() if r != args.round]
    codes = {}
    if ids:
        codes = {boards.municipality_key(s.municipality): s.municipality_code for s in archive.load(ids[-1]).stations}
    raw, summary = appdata.rebuild(client, rik_type, args.round, codes, threads=args.threads, log=log)
    meta = archive.meta(args.round)
    meta.setdefault("kind", info.get("kind", "unknown"))
    meta.setdefault("rik_type", rik_type)
    meta.setdefault("contest", {})
    meta["title"] = meta.get("title") or summary["title"] or info.get("name") or args.round
    if not meta.get("contestants"):
        meta["contestants"] = summary["contestants"]
    meta["source"] = "results_app"
    archive.save_meta(args.round, meta)
    when = now_iso()
    result = archive.add_snapshot(args.round, raw, fetched=when, rik_time=summary["rik_time"],
                                  total=summary["stations"], filename="rebuilt-from-results-app.csv")
    if result is None:
        log(f"{args.round}: same as the archived version")
        return 0
    n = after_change(archive, args.round, when, args.notes, notify=False, announce=False)
    log(f"{args.round}: archived {summary['stations']} stations, {n} flags")
    if args.commit and commit([str(args.data), str(args.notes)], f"Data: {args.round} rebuilt from RIK's results app"):
        if args.push and push() and args.dispatch_pages:
            dispatch_pages()
    return 0


def cmd_import_table(args) -> int:
    """Archive a round from RIK's station table (Excel), for rounds before RIK's results app.

    The round's meta.json (kind, type, date, titles) is written by hand first."""
    from izbori import tables
    archive = Archive(args.data)
    ids = [r for r in archive.round_ids() if r != args.round]
    known: dict[str, tuple[str, str]] = {}
    if ids:
        for s in archive.load(ids[-1]).stations:
            known.setdefault(s.municipality_code, (s.district, s.district_code))
    raw, info = tables.table_rows(tables.read_xls(Client().get_bytes(args.url)), known)
    if info["stations"] < args.min_stations:
        log(f"{args.round}: only {info['stations']} stations in the table, not archived")
        return 1
    meta = archive.meta(args.round)
    meta.setdefault("contest", {})
    if not meta.get("contestants"):
        meta["contestants"] = info["contestants"]
    meta["source"] = "rik_table"
    meta["table"] = args.url
    archive.save_meta(args.round, meta)
    when = now_iso()
    name = args.url.rsplit("/", 1)[-1].rsplit(".", 1)[0] + ".csv"
    result = archive.add_snapshot(args.round, raw, fetched=when, rik_time=tables.rik_time(args.url),
                                  total=info["stations"], filename=name)
    if result is None:
        log(f"{args.round}: same as the archived version")
        return 0
    n = after_change(archive, args.round, when, args.notes, notify=False, announce=False)
    log(f"{args.round}: archived {info['stations']} stations, {len(info['contestants'])} contestants, {n} flags")
    if args.commit and commit([str(args.data), str(args.notes)], f"Data: {args.round} from RIK's station table"):
        if args.push and push() and args.dispatch_pages:
            dispatch_pages()
    return 0


def cmd_site(args) -> int:
    from izbori.site import Site
    site = Site(Archive(args.data), Path(args.out), args.notes, args.site_url, incremental=args.incremental)
    out = site.build()
    print(f"site written to {out}: {site.rendered} files written, {site.kept} pages kept from the previous build")
    return 0


def cmd_targets(args) -> int:
    from izbori import targets
    rows = targets.rank(Archive(args.data), args.notes)
    targets.write_csv(rows, Path(args.out), args.lang)
    if args.html:
        targets.write_html(rows, Path(args.html), args.lang)
    print(f"{len(rows)} stations ranked → {args.out}" + (f" and {args.html}" if args.html else ""))
    print("Keep the group's own plans (who goes where) out of the repository.")
    return 0


def cmd_check(args) -> int:
    a = analyze(Archive(args.data), args.round, args.notes)
    counts = Counter(f.code for f in a.flags)
    print(f"{latin(a.round.title)}: {a.totals.counted}/{a.totals.stations} counted, "
          f"{len(a.by_station)} stations flagged")
    for code, n in counts.most_common():
        print(f"  {n:>5}  {latin(check_name(code, 'cyr'))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="izbori", description=__doc__)
    p.add_argument("--data", type=Path, default=Path("data"), help="archive folder (default: data)")
    p.add_argument("--notes", type=Path, default=Path("notes"), help="news notes folder (default: notes)")
    p.add_argument("--site-url", default=SITE_URL, help="public address of the site")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("rounds", help="list the elections and rounds RIK offers").set_defaults(fn=cmd_rounds)

    f = sub.add_parser("fetch", help="download one round now and archive it if it changed")
    f.add_argument("round")
    f.add_argument("--type", type=int, help="RIK's election type, if the round isn't known yet")
    f.set_defaults(fn=cmd_fetch)

    i = sub.add_parser("import", help="archive a results file downloaded from RIK by hand")
    i.add_argument("file")
    i.add_argument("--round", required=True)
    i.add_argument("--kind", default="unknown",
                   choices=["presidential", "parliamentary", "local", "provincial", "unknown"])
    i.add_argument("--type", type=int)
    i.add_argument("--title")
    i.add_argument("--contestants", help="JSON list of {name, short, minority} in ballot order")
    i.add_argument("--fetched", help="ISO time the file was downloaded (default: from its name)")
    i.add_argument("--rik-time", help="RIK's timestamp for the file")
    i.set_defaults(fn=cmd_import)

    u = sub.add_parser("update", help="check RIK, archive what changed; with --watch, keep going while counting")
    u.add_argument("--watch", action="store_true")
    u.add_argument("--every", type=int, default=180, help="seconds between checks while watching")
    u.add_argument("--max-minutes", type=float, default=345)
    u.add_argument("--commit", action="store_true", help="commit archive changes to git")
    u.add_argument("--push", action="store_true")
    u.add_argument("--dispatch-pages", action="store_true", help="start the pages workflow after a push")
    u.add_argument("--notify", action="store_true", help="send the email digest if SMTP settings are present")
    u.add_argument("--always", action="store_true", help="ask RIK now, whatever the election calendar says")
    u.add_argument("--rerun", action="store_true",
                   help="when the watch time is up and a count is still open, start the update workflow again")
    u.set_defaults(fn=cmd_update)

    b = sub.add_parser("boards", help="read which lists appointed members to extended polling boards")
    b.add_argument("--round", help="round id (default: the newest round RIK lists)")
    b.add_argument("--type", type=int, help="RIK's election type, if the round isn't known yet")
    b.add_argument("--workers", type=int, help="parallel OCR processes (default: number of CPUs)")
    b.add_argument("--budget-minutes", type=float, default=320, help="stop starting new documents after this")
    b.add_argument("--limit", type=int, help="read at most this many decisions (for trials)")
    b.add_argument("--show", type=int, default=0, help="print this many station summaries (no names)")
    b.add_argument("--diagnose", type=int, default=0, help="log the masked layout of this many unreadable decisions")
    b.add_argument("--retry-unparsed", action="store_true", help="read unreadable decisions again")
    b.add_argument("--plan", metavar="FILE", help="index the register and write what to read to FILE, then stop")
    b.add_argument("--read", metavar="FILE", help="read one part (--shard) of a plan's decisions into --out")
    b.add_argument("--shard", default="0/1", help="which part of the plan to read, as I/N")
    b.add_argument("--out", default="part.json", help="where --read writes what it read")
    b.add_argument("--merge", metavar="FILE", help="keep a plan and the parts read for it in the round's store")
    b.add_argument("parts", nargs="*", help="with --merge: the parts written by --read")
    b.add_argument("--commit", action="store_true")
    b.add_argument("--push", action="store_true")
    b.add_argument("--dispatch-pages", action="store_true")
    b.set_defaults(fn=cmd_boards)

    d = sub.add_parser("documents", help="read RIK's register of minutes: observers' records, remarks, rulings")
    d.add_argument("--round", help="one round, read in full (default: rounds due, see cmd_documents)")
    d.add_argument("--all", action="store_true", help="every archived round")
    d.add_argument("--recent-days", type=int, default=60)
    d.add_argument("--threads", type=int, default=3)
    d.add_argument("--notify", action="store_true", help="queue the email digest for new flags")
    d.add_argument("--commit", action="store_true")
    d.add_argument("--push", action="store_true")
    d.add_argument("--dispatch-pages", action="store_true")
    d.set_defaults(fn=cmd_documents)

    g = sub.add_parser("geo", help="municipal boundaries from OpenStreetMap, for the map on the Explore page")
    g.add_argument("--out", help="default: <data>/geo/municipalities.json")
    g.add_argument("--commit", action="store_true")
    g.add_argument("--push", action="store_true")
    g.add_argument("--dispatch-pages", action="store_true")
    g.set_defaults(fn=cmd_geo)

    o = sub.add_parser("observers", help="observers' records: score them with OCR, or list them to review")
    o.add_argument("--round", help="round id (default: the newest)")
    o.add_argument("--review", action="store_true", help="write the list to read, most written-in first")
    o.add_argument("--out", default="observers-review.csv")
    o.add_argument("--html")
    o.add_argument("--merge", metavar="CSV",
                   help="copy the rows of a filled-in review list that have a yes or no into observer_reviews.csv")
    o.add_argument("--workers", type=int, help="parallel OCR processes (default: number of CPUs)")
    o.add_argument("--budget-minutes", type=float, default=320, help="stop starting new records after this")
    o.add_argument("--limit", type=int, help="read at most this many records (for trials)")
    o.add_argument("--diagnose", type=int, default=0, help="log the numbers behind this many scores")
    o.add_argument("--layout", action="store_true",
                   help="with --diagnose, also log each record's layout, every word not printed on the form masked")
    o.add_argument("--station", action="append",
                   help="only this station (municipality code/number), read again if scored before; repeatable")
    o.add_argument("--commit", action="store_true")
    o.add_argument("--push", action="store_true")
    o.set_defaults(fn=cmd_observers)

    a = sub.add_parser("import-app", help="rebuild a finished round from RIK's results app, station by station")
    a.add_argument("--round", required=True)
    a.add_argument("--type", type=int, help="RIK's election type, if the round isn't known yet")
    a.add_argument("--threads", type=int, default=4)
    a.add_argument("--commit", action="store_true")
    a.add_argument("--push", action="store_true")
    a.add_argument("--dispatch-pages", action="store_true")
    a.set_defaults(fn=cmd_import_app)

    t = sub.add_parser("import-table", help="archive a round from RIK's station table (Excel), before the results app")
    t.add_argument("--round", required=True)
    t.add_argument("--url", required=True, help="the table's path or address on RIK's site")
    t.add_argument("--min-stations", type=int, default=1000)
    t.add_argument("--commit", action="store_true")
    t.add_argument("--push", action="store_true")
    t.add_argument("--dispatch-pages", action="store_true")
    t.set_defaults(fn=cmd_import_table)

    s = sub.add_parser("site", help="build the static site")
    s.add_argument("--out", default="_site")
    s.add_argument("--incremental", action="store_true",
                   help="keep the previous build in --out and render only the pages whose data changed")
    s.set_defaults(fn=cmd_site)

    t = sub.add_parser("targets", help="ranked list of stations to watch, as a file for observer groups")
    t.add_argument("--out", default="targets.csv")
    t.add_argument("--html")
    t.add_argument("--lang", default="lat", choices=["lat", "cyr", "en"])
    t.set_defaults(fn=cmd_targets)

    c = sub.add_parser("check", help="print the flags for one archived round")
    c.add_argument("round")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
