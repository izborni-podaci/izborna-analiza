"""When to ask RIK for results: often around an election, once a day otherwise.

Election days come from the archive (each round's date, from its first results) and from data/elections.csv,
where a maintainer enters an election once it is called: RIK lists the new round weeks before election day, but
without the date. The columns are date (YYYY-MM-DD), round (RIK's id, if it is listed yet), kind and note.

How often the hourly run asks RIK, by the nearest election:
- while a count is open: every run (and the run keeps watching, see `izbori update --watch`);
- on election day every 6 hours until two hours before the polls close, then every hour until two days after;
- until 14 days after: every 3 hours (late results, corrections, repeated votes);
- otherwise once a day, which also finds a newly called election in RIK's list of rounds;
- a round RIK lists without a known election day is looked at every hour on Sundays, when elections are held, in
  case its date wasn't entered.

The time of the last look is kept in data/looks.json, so a run GitHub skipped (its schedule is best effort and
drops many hourly runs) doesn't push the next look a whole period away."""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from izbori.i18n import BELGRADE

ELECTIONS = "elections.csv"
LOOKS = "looks.json"
FIELDS = ["date", "round", "kind", "note"]
SLACK = timedelta(minutes=20)  # the hourly run drifts; a look due within this much is taken now
POLLS_CLOSE = 20  # Belgrade time; results start an hour or two later


def calendar(root: Path) -> list[tuple[date, str]]:
    """Election days a maintainer entered, with RIK's round id where known."""
    p = Path(root) / ELECTIONS
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                day = date.fromisoformat((row.get("date") or "").strip())
            except ValueError:
                continue
            out.append((day, (row.get("round") or "").strip()))
    return out


def upcoming(root: Path, today: date) -> list[dict]:
    """The next election day a maintainer entered (today counts), one row per election held that day, with its
    kind and note; empty when none is ahead."""
    p = Path(root) / ELECTIONS
    if not p.exists():
        return []
    rows = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                day = date.fromisoformat((row.get("date") or "").strip())
            except ValueError:
                continue
            if day >= today:
                rows.append({"day": day, "kind": (row.get("kind") or "").strip(),
                             "note": (row.get("note") or "").strip()})
    if not rows:
        return []
    first = min(r["day"] for r in rows)
    return [r for r in rows if r["day"] == first]


# Deadlines counted back from voting day, as the law states them (Law on the Election of Members of Parliament,
# Arts. 34, 161, 88 and 6; the Law on Local Elections has the same ones for polling boards, Art. 27). A rule of N
# days ends at midnight N days before; one of hours counts back from midnight starting voting day.
DEADLINES = [("boards_proposed", 15), ("boards_appointed", 10), ("observers_domestic", 7)]


def deadlines(day: date, today: date) -> list[tuple[str, date]]:
    """The deadlines still ahead for an election on `day`, in order: proposals and appointments of polling boards,
    domestic observers' registration, the handover of materials (24 hours before voting day, so by the end of the
    day two days before) and campaign silence (from the start of the day two days before)."""
    out = [(key, day - timedelta(days=n)) for key, n in DEADLINES]
    out += [("handover", day - timedelta(days=2)), ("silence", day - timedelta(days=2))]
    return [(key, d) for key, d in out if d >= today]


def election_days(archive) -> list[tuple[date, str]]:
    """Every known election day: the archived rounds' and the calendar's."""
    out = []
    for rid in set(archive.known_rounds()) | set(archive.round_ids()):
        d = archive.meta(rid).get("date")
        if d:
            out.append((date.fromisoformat(d[:10]), rid))
    return out + calendar(archive.root)


def undated(archive) -> list[str]:
    """Rounds RIK lists with no known election day (no results yet, and not in the calendar)."""
    named = {rid for _, rid in calendar(archive.root) if rid}
    return sorted(rid for rid in archive.known_rounds()
                  if not archive.meta(rid).get("date") and rid not in named)


def every(archive, now: datetime) -> tuple[timedelta, str]:
    """How long between looks at RIK now, and why."""
    local = now.astimezone(BELGRADE)
    today = local.date()
    for rid in set(archive.known_rounds()) | set(archive.round_ids()):
        day = archive.meta(rid).get("date")
        recent = not day or (today - date.fromisoformat(day[:10])).days <= 30  # a count left open for good isn't
        if archive.state(rid).get("counting") and recent:
            return timedelta(0), f"the count of {rid} is open"
    wait, why = timedelta(days=1), "no election under way"
    for day, rid in election_days(archive):
        age = (today - day).days
        if (age == 0 and local.hour >= POLLS_CLOSE - 2) or 1 <= age <= 2:
            return timedelta(hours=1), f"the election of {day.isoformat()}"
        if age == 0 and wait > timedelta(hours=6):
            wait, why = timedelta(hours=6), f"election day {day.isoformat()}, before the polls close"
        if 3 <= age <= 14 and wait > timedelta(hours=3):
            wait, why = timedelta(hours=3), f"{age} days after the election of {day.isoformat()}"
    if wait == timedelta(days=1) and today.weekday() == 6 and undated(archive):
        return timedelta(hours=1), f"a Sunday, and RIK lists rounds without a known election day: {undated(archive)}"
    return wait, why


def looks(root: Path) -> dict[str, str]:
    p = Path(root) / LOOKS
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def since(root: Path, what: str, now: datetime) -> timedelta | None:
    """How long ago RIK was last asked for `what` ("rik", "settled", "refresh"); None if never."""
    when = looks(root).get(what)
    return now - datetime.fromisoformat(when) if when else None


def due(root: Path, what: str, now: datetime, period: timedelta) -> bool:
    ago = since(root, what, now)
    return ago is None or ago + SLACK >= period


def record(root: Path, now: datetime, *whats: str) -> None:
    data = looks(root)
    for what in whats:
        data[what] = now.astimezone(UTC).isoformat(timespec="seconds")
    (Path(root) / LOOKS).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def write_template(root: Path) -> Path:
    p = Path(root) / ELECTIONS
    if not p.exists():
        with p.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(FIELDS)
    return p
