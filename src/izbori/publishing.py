"""What reached RIK's registers for each municipality's polling stations and from its electoral commission, and
when: the facts behind the page on the municipal commissions.

There is no score. Each column is a fact read from RIK's registers, and a highlighted cell is a question, not a
grade: municipalities differ in size and in how far their materials travel.

- Minutes: stations whose minutes (RG-2, not a repeat vote's) RIK published, and how many hours after the polls
  closed (20:00 on election day) the first of them was uploaded. The upload time is the stamp RIK puts in every
  document's link; the register of minutes shows the same time for almost every document, and where it differs it
  shows a later one (an entry edited days after the file came).
- Corrections: stations with a ruling correcting the minutes (RG-7).
- Polling boards: stations whose decision on the standing, or the extended, composition is in RIK's register of
  additional documents, as placed by `boards.Placer`.
- The commission's own documents (minutes of its sessions, reports, decisions) in the same register, and apart
  from them its city's commission's (commission.city_parts): Niš's for its city municipalities, Požarevac's for
  Kostolac.
- Changes: stations with a flag of the "change" group (numbers, minutes or corrections changed after publication).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median

from izbori.documents import uploaded_at

POLLS_CLOSE = "20:00"
LATE_HOURS = 24  # minutes uploaded later than this after the polls closed are counted on their own
SLOW_HOURS = 12  # a median above this: most of the municipality's minutes only came the next day


@dataclass
class Row:
    code: str
    name: str
    district: str
    stations: int
    minutes: int = 0  # stations whose minutes RIK published
    hours: float | None = None  # median hours from the polls closing to a station's first minutes
    late: int = 0  # stations whose first minutes came more than LATE_HOURS after the polls closed
    corrections: int = 0  # stations with a ruling correcting the minutes
    standing: int | None = None  # stations with a decision on the standing composition; None if not read
    extended: int | None = None  # the same for the extended composition
    cdocs: int | None = None  # the commission's own documents; None if the register wasn't read
    city: int = 0  # its city's commission's documents, shared by the city's municipalities
    changed: int = 0  # stations with a flag of the change group
    warn: set[str] = field(default_factory=set)  # columns to highlight

    def share(self, n: int | None) -> float | None:
        return n / self.stations if n is not None and self.stations else None


def closing(date: str) -> datetime | None:
    """When the polls closed: 20:00 on election day, Belgrade time, as RIK's upload times are."""
    return datetime.fromisoformat(f"{date}T{POLLS_CLOSE}") if date else None


def first_minutes(docs) -> str:
    """Upload time of a station's first minutes, a repeat vote's left out, from the stamp in the link (else the
    register's time); "" when none has a time."""
    times = (uploaded_at(d.url) or d.uploaded for d in docs if d.kind == "minutes" and not d.repeat)
    return min((x for x in times if x), default="")


def hours_after(uploaded: str, close: datetime | None) -> float | None:
    if not uploaded or close is None:
        return None
    return (datetime.fromisoformat(uploaded[:16]) - close).total_seconds() / 3600


def rows(municipalities: list[dict], stations_by_code: dict[str, list], documents: dict, close: datetime | None,
         board_docs: dict | None, commission_docs: dict[str, int] | None, changed: set[str],
         city_docs: dict[str, int] | None = None) -> list[Row]:
    """One row per municipality in Serbia (abroad and prisons are RIK's own). board_docs: station key → its
    decisions (documents.Doc), None when the round's decisions weren't read; commission_docs: municipality code →
    its commission's documents, None when that register wasn't read; changed: station keys with a change flag;
    city_docs: city municipality code → its city's commission's documents."""
    out = []
    for m in municipalities:
        if m["kind"] != "domestic":
            continue
        sts = stations_by_code.get(m["code"], [])
        row = Row(m["code"], m["name"], m.get("district", ""), len(sts))
        hours = []
        for s in sts:
            docs = documents.get(s.key, [])
            first = first_minutes(docs)
            if any(d.kind == "minutes" and not d.repeat for d in docs):
                row.minutes += 1
            h = hours_after(first, close)
            if h is not None:
                hours.append(h)
                row.late += h > LATE_HOURS
            row.corrections += any(d.kind == "correction" for d in docs)
            row.changed += s.key in changed
        row.hours = median(hours) if hours else None
        if board_docs is not None:
            kinds = [{d.kind for d in board_docs.get(s.key, [])} for s in sts]
            row.standing = sum("board_standing" in k for k in kinds)
            row.extended = sum("board_extended" in k for k in kinds)
        if commission_docs is not None:
            row.cdocs = commission_docs.get(m["code"], 0)
            row.city = (city_docs or {}).get(m["code"], 0)
        out.append(row)
    _highlight(out)
    return out


def _highlight(out: list[Row]) -> None:
    """Mark the cells worth a question: minutes or board decisions missing from RIK's registers, most minutes only
    the next day, some later than a day, numbers changed after publication. The rules are absolute, so a
    municipality isn't marked only for being slower than others. No document from the commission isn't marked:
    a city municipality may have none of its own where its city's commission runs the vote."""
    for r in out:
        if r.minutes < r.stations:
            r.warn.add("minutes")
        if r.hours is not None and r.hours > SLOW_HOURS:
            r.warn.add("hours")
        if r.late:
            r.warn.add("late")
        for col in ("standing", "extended"):
            n = getattr(r, col)
            if n is not None and n < r.stations:
                r.warn.add(col)
        if r.changed:
            r.warn.add("changed")


def summary(out: list[Row], documents: dict, stations: list, close: datetime | None, unplaced: int = 0,
            city: int = 0) -> dict:
    """The whole country in one line per column: totals, and the median over every station, not over the
    municipalities. city: the documents RIK lists under a city the results don't have, each once (Niš's); unplaced:
    those under a name no municipality takes."""
    hours = [h for s in stations if s.kind == "domestic"
             and (h := hours_after(first_minutes(documents.get(s.key, [])), close)) is not None]
    known = lambda col: [getattr(r, col) for r in out if getattr(r, col) is not None]  # noqa: E731
    return {"municipalities": len(out), "stations": sum(r.stations for r in out),
            "minutes": sum(r.minutes for r in out), "hours": median(hours) if hours else None,
            "late": sum(r.late for r in out), "corrections": sum(r.corrections for r in out),
            "standing": sum(known("standing")) if known("standing") else None,
            "extended": sum(known("extended")) if known("extended") else None,
            "cdocs": sum(known("cdocs")) if known("cdocs") else None,
            "city": city, "unplaced": unplaced, "changed": sum(r.changed for r in out)}


COLUMNS = ["code", "municipality", "district", "stations", "minutes", "median_hours", "late", "corrections",
           "standing", "extended", "commission_documents", "city_commission_documents", "changed"]


def to_csv(out: list[Row]) -> str:
    """The table as CSV, names as RIK writes them; empty where the register wasn't read."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    blank = lambda v: "" if v is None else v  # noqa: E731
    for r in out:
        w.writerow([r.code, r.name, r.district, r.stations, r.minutes,
                    "" if r.hours is None else f"{r.hours:.1f}", r.late, r.corrections, blank(r.standing),
                    blank(r.extended), blank(r.cdocs), "" if r.cdocs is None else r.city, r.changed])
    return buf.getvalue()
