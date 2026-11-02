"""Everything the site, feeds, email and target list need about one archived round."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from izbori.checks import Flag, group_by_station, station_flags
from izbori.contests import Presidential, Proportional, Totals, evaluate
from izbori.history import Archive
from izbori.model import Round
from izbori.notes import Note, load_notes


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
    previous_ids = earlier_rounds(archive, rid)
    previous = [load(r) for r in previous_ids]
    changes = archive.changes(rid)
    flags = station_flags(rnd, changes, previous)
    totals, contest = evaluate(rnd)
    return Analysis(
        round=rnd, totals=totals, contest=contest, flags=flags, changes=changes,
        snapshots=archive.snapshots(rid), notes=load_notes(notes_dir, rid) if notes_dir else {},
        flags_seen=archive.flags_seen(rid), previous=previous_ids,
    )


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
