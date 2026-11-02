"""Command line: izbori rounds | fetch | import | update | site | targets | check."""

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

from izbori import feed, mail
from izbori.config import SITE_URL
from izbori.history import Archive, now_iso
from izbori.i18n import BELGRADE, check_name, parse_time
from izbori.notes import write_template
from izbori.report import analyze, record_new_flags
from izbori.rik import Client, RikError, Summary, guess_kind
from izbori.translit import latin

REFRESH_HOUR_UTC = 3  # once a day, re-download every round even if RIK's progress looks unchanged
WATCH_REFRESH = timedelta(minutes=15)  # while watching, re-download at least this often


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


def after_change(archive: Archive, rid: str, when: str, notes_dir: Path, notify: bool) -> int:
    """Record new flags, add a feed entry and queue an email. Returns the number of new flags."""
    a = analyze(archive, rid, notes_dir)
    new = record_new_flags(archive, a, when)
    if new:
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


def cmd_update(args) -> int:
    archive = Archive(args.data)
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
        force = first and datetime.now(UTC).hour == REFRESH_HOUR_UTC
        for rid, info in sorted(found.items()):
            try:
                did, summ, finished = fetch_round(client, archive, rid, info, args.notes, args.notify, force=force,
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
            log("watch time is up; the next scheduled run continues")
            break
        time.sleep(args.every)
    return 0


def cmd_boards(args) -> int:
    """Read which lists appointed members to the extended polling boards (controllers)."""
    import os
    from izbori import boards
    archive = Archive(args.data)
    client = Client()
    known = archive.known_rounds()
    if not known:
        known = client.all_rounds()
        archive.save_known_rounds(known)
    rid = args.round or max(known, key=lambda r: int(r) if r.isdigit() else 0)
    info = known.get(rid) or {"type": args.type or 2, "name": "", "kind": "unknown"}
    meta = archive.meta(rid)
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
    last_commit = [time.monotonic()]

    def checkpoint():
        if args.commit and time.monotonic() - last_commit[0] > 1800:
            if commit([str(args.data)], f"Boards: {rid} ({now_iso()})") and args.push:
                push()
            last_commit[0] = time.monotonic()

    result = boards.run(archive.dir(rid), rid, int(info["type"]), contestants, stations, client,
                        workers=args.workers or os.cpu_count() or 2, budget_seconds=args.budget_minutes * 60,
                        limit=args.limit, log=log, checkpoint=checkpoint)
    if args.show:
        cov = boards.coverage(boards.load_store(archive.dir(rid)))
        for key in sorted(cov)[: args.show]:
            c = cov[key]
            members = sorted(int(n) for n, v in c["lists"].items() if v["member"])
            log(f"{key}: lists with a member {members} of {len(contestants)}; unmatched {c['unmatched']}; "
                f"address: {latin(c['address'])}")
        log(f"stations with a decision read: {len(cov)}")
    if args.commit and commit([str(args.data)], f"Boards: {rid}, {result['read']} decisions read ({now_iso()})"):
        if args.push and push() and args.dispatch_pages:
            dispatch_pages()
    return 0


def cmd_site(args) -> int:
    from izbori.site import build
    out = build(Archive(args.data), Path(args.out), args.notes, args.site_url)
    print(f"site written to {out}")
    return 0


def cmd_targets(args) -> int:
    from izbori import targets
    rows = targets.rank(Archive(args.data), args.notes)
    targets.write_csv(rows, Path(args.out), args.lang)
    if args.html:
        targets.write_html(rows, Path(args.html), args.lang)
    print(f"{len(rows)} stations ranked → {args.out}" + (f" and {args.html}" if args.html else ""))
    print("This list is private: don't commit it or post it.")
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
    u.set_defaults(fn=cmd_update)

    b = sub.add_parser("boards", help="read which lists appointed members to extended polling boards")
    b.add_argument("--round", help="round id (default: the newest round RIK lists)")
    b.add_argument("--type", type=int, help="RIK's election type, if the round isn't known yet")
    b.add_argument("--workers", type=int, help="parallel OCR processes (default: number of CPUs)")
    b.add_argument("--budget-minutes", type=float, default=320, help="stop starting new documents after this")
    b.add_argument("--limit", type=int, help="read at most this many decisions (for trials)")
    b.add_argument("--show", type=int, default=0, help="print this many station summaries (no names)")
    b.add_argument("--commit", action="store_true")
    b.add_argument("--push", action="store_true")
    b.add_argument("--dispatch-pages", action="store_true")
    b.set_defaults(fn=cmd_boards)

    s = sub.add_parser("site", help="build the static site")
    s.add_argument("--out", default="_site")
    s.set_defaults(fn=cmd_site)

    t = sub.add_parser("targets", help="private ranked list of stations to watch (never commit it)")
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
