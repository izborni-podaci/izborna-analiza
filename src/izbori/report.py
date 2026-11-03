"""Everything the site, feeds, email and target list need about one archived round."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from izbori import boards, documents, observers
from izbori.checks import Flag, group_by_station, station_flags
from izbori.contests import Presidential, Proportional, Totals, evaluate
from izbori.history import Archive
from izbori.model import Round
from izbori.notes import Note, load_notes
from izbori.places import RULES_FILE, Places, follow, load_rules


@dataclass
class Analysis:
    round: Round
    totals: Totals
    contest: Proportional | Presidential | None
    flags: list[Flag]
    changes: list[dict]
    snapshots: list[dict]
    notes: dict[str, list[Note]]
    flags_seen: dict
    previous: list[str] = field(default_factory=list)
    documents: dict = field(default_factory=dict)  # station key → documents.Doc list: minutes, observers, remarks…
    reviews: dict = field(default_factory=dict)  # station key → observers.Review: a person read the observers' record

    @property
    def by_station(self) -> dict[str, list[Flag]]:
        return group_by_station(self.flags)

    @property
    def counting(self) -> bool:
        return self.totals.counted < self.totals.stations


def earlier_rounds(archive: Archive, rid: str) -> list[str]:
    ids = archive.round_ids()
    if rid not in ids:
        return []
    return list(reversed(ids[: ids.index(rid)]))


def analyze(archive: Archive, rid: str, notes_dir: Path | None = None, cache: dict | None = None) -> Analysis:
    cache = cache if cache is not None else {}

    def load(r: str) -> Round:
        if r not in cache:
            cache[r] = archive.load(r)
        return cache[r]

    rnd = load(rid)
    # compare with earlier rounds of the same kind first (parliamentary with parliamentary), newest first
    previous_ids = earlier_rounds(archive, rid)
    kind = archive.meta(rid).get("kind")
    previous_ids.sort(key=lambda r: archive.meta(r).get("kind") != kind)
    previous = [load(r) for r in previous_ids]
    changes = archive.changes(rid)
    docs = station_documents(archive, rnd)
    reviews = observers.load_reviews(archive.dir(rid))
    flags = station_flags(rnd, changes, previous, links(archive, rid, cache), docs, reviews)
    totals, contest = evaluate(rnd)
    return Analysis(
        round=rnd, totals=totals, contest=contest, flags=flags, changes=changes,
        snapshots=archive.snapshots(rid), notes=load_notes(notes_dir, rid) if notes_dir else {},
        flags_seen=archive.flags_seen(rid), previous=previous_ids, documents=docs, reviews=reviews,
    )


def station_documents(archive: Archive, rnd: Round) -> dict[str, list]:
    """Each station's documents: those in the results file and those in RIK's register of minutes, each once."""
    register = documents.load(archive.dir(rnd.id))
    out = {}
    for s in rnd.stations:
        docs = documents.for_station(s.minutes_links + s.correction_links, register.get(s.key))
        if docs:
            out[s.key] = docs
    return out


def addresses(archive: Archive, rid: str, cache: dict) -> dict[str, str]:
    key = ("addresses", rid)
    if key not in cache:
        cache[key] = boards.addresses(boards.load_store(archive.dir(rid)))
    return cache[key]


def links(archive: Archive, rid: str, cache: dict | None = None) -> Places:
    """The places from the first archived round up to this one, with addresses and the manual corrections. They
    run forward in time, so they agree with the places the site shows for these rounds."""
    cache = cache if cache is not None else {}
    ids = archive.round_ids()
    ids = ids[: ids.index(rid) + 1] if rid in ids else [rid]
    rounds = []
    for r in ids:
        if r not in cache:
            cache[r] = archive.load(r)
        rounds.append((r, cache[r].stations, addresses(archive, r, cache)))
    return follow(rounds, load_rules(archive.root / RULES_FILE))


def record_new_flags(archive: Archive, analysis: Analysis, when: str) -> list[str]:
    """Remember when each flag first appeared; return the ids that are new."""
    seen = archive.flags_seen(analysis.round.id)
    new = [f.id for f in analysis.flags if f.id not in seen]
    for fid in new:
        seen[fid] = when
    if new:
        archive.save_flags_seen(analysis.round.id, seen)
        analysis.flags_seen = seen
    return new
