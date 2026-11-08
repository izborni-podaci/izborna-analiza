"""Everything the site, feeds, email and target list need about one archived round."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path

from izbori import boards, documents, observers, settlements
from izbori.checks import Flag, group_by_station, station_flags
from izbori.contests import Presidential, Proportional, Totals, evaluate
from izbori.history import Archive
from izbori.model import Round, links as link_pairs
from izbori.notes import Note, load_notes
from izbori.places import RULES_FILE, Places, contradicts, follow, load_rules


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
    docs = station_documents(archive, rnd, changes)
    reviews = observers.load_reviews(archive.dir(rid))
    flags = station_flags(rnd, changes, previous, links(archive, rid, cache), docs, reviews,
                          settlements.load_store(archive.dir(rid)).get("stations"))
    totals, contest = evaluate(rnd)
    return Analysis(
        round=rnd, totals=totals, contest=contest, flags=flags, changes=changes,
        snapshots=archive.snapshots(rid), notes=load_notes(notes_dir, rid) if notes_dir else {},
        flags_seen=archive.flags_seen(rid), previous=previous_ids, documents=docs, reviews=reviews,
    )


def station_documents(archive: Archive, rnd: Round, changes: list[dict] | None = None) -> dict[str, list]:
    """Each station's documents: those in the results file and those in RIK's register of minutes, each once.
    When the results file's link to the minutes changed, the earlier minutes stay on the station as a document,
    so both versions can be opened and compared; a replacement is not a warning (a commission re-uploading its
    whole municipality's minutes says nothing about any one station's numbers)."""
    register = documents.load(archive.dir(rnd.id))
    previous: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for e in changes or []:
        if e["f"] == "zapisnik_link" and e["o"] and e["n"] != e["o"]:
            previous[e["s"]].extend((label, url, e["t"]) for label, url in link_pairs(e["o"]))
    out = {}
    for s in rnd.stations:
        docs = documents.for_station(s.minutes_links + s.correction_links, register.get(s.key))
        seen = {documents.path_of(d.url) for d in docs}
        for label, url, when in previous.get(s.key, []):
            if documents.path_of(url) not in seen:
                seen.add(documents.path_of(url))
                docs.append(documents.Doc("minutes_previous", documents.doc(label, url).repeat, label, url, when))
        docs = documents.order(docs)
        if docs:
            out[s.key] = docs
    return out


def addresses(archive: Archive, rid: str, cache: dict) -> dict[str, str]:
    """Per station, the address on its decisions, unless it names another building than the results do."""
    key = ("addresses", rid)
    if key not in cache:
        if rid not in cache:
            cache[rid] = archive.load(rid)
        names = {s.key: s.name for s in cache[rid].stations}
        found = boards.addresses(boards.load_store(archive.dir(rid)))
        cache[key] = {k: a for k, a in found.items() if not contradicts(names.get(k, ""), a)}
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
