"""Results and controllers by the kind of settlement a polling station is in: the round's "Settlements" page.

A station with a settlement (settlements.py) falls in one class of each dimension, by its settlement's figures in the
2022 census (settlements.Figures):

- type: RZS's urban settlements and the other ones;
- size: the population in 2022: under 500, 500 to 1,999, 2,000 to 9,999, 10,000 to 99,999, 100,000 or more;
- change: the population from 2011 to 2022: down by more than 20%, by 10 to 20%, by less than 10%, the same or
  more.

Each class gives its stations, settlements, registered voters and turnout; every contestant's share of the valid votes
cast there (votes added up over the class's counted stations); and, where the decisions on polling boards were read,
the share of the class's stations where the contestant had a controller, a member or a deputy of the extended
composition (as Explore counts it), shown where a decision was read for at least half of the class's stations, and
at least 10 (Belgrade's decisions of 2024 were mostly never published). Between urban and other settlements it also
gives the difference within
municipalities: in each municipality with counted stations of both kinds, other minus urban, averaged with the
smaller side's number of stations as the weight, so that a contestant strong in rural municipalities isn't read as
strong in villages everywhere.

The same rules for every contestant, in the order of their votes in the whole election; nothing is ranked or flagged.
Stations with no settlement (no address in the decisions, Kosovo and Metohija, abroad, prisons) are left out and
counted: unknown is not zero. Explore uses the same classes (CLASSES) for its filters."""

from __future__ import annotations

import csv
import io
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from izbori.settlements import Figures

SIZE = (500, 2000, 10000, 100000)  # population in 2022
CHANGE = (-0.20, -0.10, 0.0)  # population change from 2011 to 2022, as a fraction
OLD = (0.20, 0.25, 0.30)  # share of the people aged 65 or more: only Explore's filter uses it
CLASSES = {"size": SIZE, "change": CHANGE, "old": OLD}
READ_MIN = 10  # a class's controllers are shown where at least this many of its stations' decisions were read,
READ_SHARE = 0.5  # and at least this share of them
DIMENSIONS = ("type", "size", "change")
CSV_CLASSES = {"type": ("urban", "other"), "size": ("<500", "500-1999", "2000-9999", "10000-99999", ">=100000"),
               "change": ("<-20%", "-20%..-10%", "-10%..0%", ">=0%")}


def klass(value: float | None, bounds: tuple) -> int | None:
    """The class of a value: how many of the bounds it reaches, so each class runs from its bound up to the next."""
    return None if value is None else bisect_right(bounds, value)


def classes_of(f: Figures) -> dict[str, int | None]:
    """A settlement's class in each dimension; None where the census doesn't give the figure."""
    return {"type": 0 if f.urban else 1, "size": klass(f.pop2022, SIZE), "change": klass(f.change, CHANGE)}


@dataclass
class Group:
    """What the stations of one class add up to."""
    n: int  # contestants
    stations: int = 0
    places: set = field(default_factory=set)
    registered: int = 0
    voted: int = 0
    valid: int = 0
    votes: list[int] = field(default_factory=list)
    read: int = 0  # stations whose decision on the extended board was read
    covered: list[int] = field(default_factory=list)  # per contestant: of those, where it had a controller

    def __post_init__(self):
        self.votes = self.votes or [0] * self.n
        self.covered = self.covered or [0] * self.n

    def add(self, s, place: tuple[str, str], has: list[bool] | None) -> None:
        self.stations += 1
        self.places.add(place)
        self.registered += s.registered or 0
        self.voted += s.voted or 0
        self.valid += s.valid or 0
        for i in range(self.n):
            self.votes[i] += (s.votes[i] if i < len(s.votes) else 0) or 0
        if has is not None:
            self.read += 1
            for i, h in enumerate(has):
                self.covered[i] += h

    def share(self, i: int) -> float | None:
        return self.votes[i] / self.valid if self.valid else None

    def coverage(self, i: int) -> float | None:
        return self.covered[i] / self.read if self.read else None

    @property
    def enough_read(self) -> bool:
        return self.read >= max(READ_MIN, READ_SHARE * self.stations)

    def view(self) -> dict:
        return {"stations": self.stations, "settlements": len(self.places), "registered": self.registered,
                "turnout": self.voted / self.registered if self.registered else None, "read": self.read,
                "enough_read": self.enough_read}


def controllers(entry: dict | None, numbers: list[int]) -> list[bool] | None:
    """Per contestant, whether it had a member or a deputy on the station's extended board; None where no decision
    was read."""
    lists = (entry or {}).get("lists")
    if lists is None:
        return None
    return [bool((lists.get(str(n)) or {}).get("member") or (lists.get(str(n)) or {}).get("deputy")) for n in numbers]


def within(pairs: list[tuple[int, float | None, float | None]]) -> float | None:
    """(weight, urban, other) per municipality → other minus urban, averaged by weight; None with nothing to compare."""
    num = den = 0.0
    for w, u, o in pairs:
        if w and u is not None and o is not None:
            num += w * (o - u)
            den += w
    return num / den if den else None


def analyse(stations: list, contestants: list, joined: dict[str, dict], figures: dict[tuple[str, str], Figures],
            coverage: dict[str, dict]) -> dict:
    """The page's numbers for one election: per dimension, each class's groups; per contestant, its shares and
    coverage by class and the urban-other difference within municipalities; and how many stations had no
    settlement."""
    n = len(contestants)
    numbers = [c.number for c in contestants]
    dims = {d: [Group(n) for _ in range(len(CSV_CLASSES[d]))] for d in DIMENSIONS}
    everything = Group(n)
    by_mun: dict[str, list[Group]] = defaultdict(lambda: [Group(n), Group(n)])  # urban, other
    used, how, without = 0, Counter(), Counter()
    total = [0] * n
    for s in stations:
        if s.counted:
            for i in range(n):
                total[i] += (s.votes[i] if i < len(s.votes) else 0) or 0
        if s.kind != "domestic" or not s.counted:
            continue
        e = joined.get(s.key)
        f = figures.get((e["u"], e["s"])) if e else None
        if f is None:
            without["none" if e is None else "figures"] += 1
            continue
        used += 1
        how[e["m"]] += 1
        place = (e["u"], e["s"])
        has = controllers(coverage.get(s.key), numbers) if coverage else None
        everything.add(s, place, has)
        for d, k in classes_of(f).items():
            if k is not None:
                dims[d][k].add(s, place, has)
        by_mun[s.municipality_code][classes_of(f)["type"]].add(s, place, has)
    order = sorted(range(n), key=lambda i: (-total[i], numbers[i]))
    both = [g for g in by_mun.values() if g[0].stations and g[1].stations]
    def shown(g: Group, i: int) -> float | None:
        return g.coverage(i) if g.enough_read else None

    rows = []
    for i in order:
        rows.append({
            "index": i, "number": numbers[i], "label": contestants[i].label,
            "votes_all": everything.share(i), "ctrl_all": shown(everything, i),
            "votes": {d: [g.share(i) for g in groups] for d, groups in dims.items()},
            "ctrl": {d: [shown(g, i) for g in groups] for d, groups in dims.items()},
            "votes_within": within([(min(u.stations, o.stations), u.share(i), o.share(i)) for u, o in both]),
            "ctrl_within": within([(min(u.read, o.read), u.coverage(i), o.coverage(i)) for u, o in both]),
        })
    return {"used": used, "how": dict(how), "without": dict(without), "municipalities_both": len(both),
            "all": everything.view(), "classes": {d: [g.view() for g in groups] for d, groups in dims.items()},
            "groups": dims, "rows": rows, "controllers": everything.enough_read}


def to_csv(result: dict, contestants: list) -> str:
    """The page's tables as one CSV: a row per dimension, class and contestant."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["dimension", "class", "number", "contestant", "stations", "settlements", "registered", "voted",
                "valid", "votes", "share", "stations_read", "with_controller", "controller_share"])
    for d in DIMENSIONS:
        for k, g in enumerate(result["groups"][d]):
            for i, c in enumerate(contestants):
                share, cov = g.share(i), g.coverage(i)
                w.writerow([d, CSV_CLASSES[d][k], c.number, c.name, g.stations, len(g.places), g.registered, g.voted,
                            g.valid, g.votes[i], "" if share is None else round(share, 6), g.read,
                            g.covered[i] if g.read else "", "" if cov is None else round(cov, 6)])
    return out.getvalue()
