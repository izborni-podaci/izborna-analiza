"""Election math: totals, presidential majority, D'Hondt seats and the votes that would change a seat."""

from __future__ import annotations

import math
from dataclasses import dataclass

from izbori.model import Round, Station

DEFAULTS = {
    "parliamentary": {"seats": 250, "threshold": 0.03, "minority_factor": 1.35, "majority": 126, "two_thirds": 167},
    "provincial": {"seats": 120, "threshold": 0.03, "minority_factor": 1.35, "majority": 61, "two_thirds": 80},
    "local": {"seats": None, "threshold": 0.03, "minority_factor": 1.35},
    "presidential": {},
    "unknown": {},
}


@dataclass
class Totals:
    stations: int
    counted: int
    registered: int
    voted: int
    ballots: int
    valid: int
    invalid: int
    votes: list[int]

    @property
    def turnout(self) -> float | None:
        return self.voted / self.registered if self.registered else None

    @property
    def invalid_share(self) -> float | None:
        return self.invalid / self.ballots if self.ballots else None

    def share_of_voted(self, i: int) -> float | None:
        return self.votes[i] / self.voted if self.voted else None

    def share_of_valid(self, i: int) -> float | None:
        return self.votes[i] / self.valid if self.valid else None


def totals(stations: list[Station], n: int) -> Totals:
    counted = [s for s in stations if s.counted]

    def add(attr: str) -> int:
        return sum(getattr(s, attr) or 0 for s in counted)

    return Totals(
        stations=len(stations),
        counted=len(counted),
        registered=add("registered"),
        voted=add("voted"),
        ballots=add("ballots"),
        valid=add("valid"),
        invalid=add("invalid"),
        votes=[sum((s.votes[i] or 0) for s in counted) for i in range(n)],
    )


@dataclass
class ListResult:
    index: int  # 0-based position on the ballot
    votes: int
    share: float  # of voters who voted, the law's base for the threshold
    over: bool
    minority: bool
    factor: float
    seats: int = 0
    gain: int | None = None  # extra votes for one more seat, others unchanged
    keep: int | None = None  # votes it could lose and keep every seat

    @property
    def takes_part(self) -> bool:
        return self.over or (self.minority and self.votes > 0)


@dataclass
class Proportional:
    seats: int
    threshold_votes: int
    lists: list[ListResult]
    majority: int | None = None
    two_thirds: int | None = None


def proportional(votes: list[int], voted: int, minority: list[bool], seats: int,
                 threshold: float = 0.03, minority_factor: float = 1.35,
                 majority: int | None = None, two_thirds: int | None = None) -> Proportional:
    """D'Hondt over lists with at least `threshold` of voters who voted; minority lists below it take part with
    their votes multiplied by `minority_factor`."""
    rows = []
    for i, v in enumerate(votes):
        over = voted > 0 and v >= threshold * voted
        is_min = bool(minority[i]) if i < len(minority) else False
        factor = minority_factor if is_min and not over else 1.0
        rows.append(ListResult(index=i, votes=v, share=v / voted if voted else 0.0, over=over, minority=is_min,
                               factor=factor))
    quotients = []
    for r in rows:
        if not r.takes_part:
            continue
        adjusted = r.votes * r.factor
        for d in range(1, seats + 1):
            quotients.append((adjusted / d, r.votes, r.index))
    quotients.sort(key=lambda q: (-q[0], -q[1]))
    won, nxt = quotients[:seats], quotients[seats:]
    by_index = {r.index: r for r in rows}
    for _, _, i in won:
        by_index[i].seats += 1
    for r in rows:
        if not r.takes_part:
            continue
        lowest_other = next((q for q in reversed(won) if q[2] != r.index), None)
        next_other = next((q for q in nxt if q[2] != r.index), None)
        if lowest_other:
            r.gain = math.floor(lowest_other[0] * (r.seats + 1) / r.factor) - r.votes + 1
        if r.seats > 0 and next_other:
            r.keep = r.votes - math.ceil(next_other[0] * r.seats / r.factor)
    return Proportional(seats=seats, threshold_votes=math.ceil(threshold * voted) if voted else 0, lists=rows,
                        majority=majority, two_thirds=two_thirds)


@dataclass
class Presidential:
    order: list[int]  # contestant indexes, most votes first
    needed: int  # more than half of voters who voted (ballots in the box, as RIK counts them)
    leader_votes: int
    leader_share: float | None
    majority: bool
    runoff: bool  # True for a two-candidate round, decided by most votes

    @property
    def leader(self) -> int | None:
        return self.order[0] if self.order else None

    @property
    def short_by(self) -> int:
        return max(0, self.needed - self.leader_votes)


def presidential(votes: list[int], voted: int) -> Presidential:
    order = sorted(range(len(votes)), key=lambda i: -votes[i])
    needed = voted // 2 + 1
    leader_votes = votes[order[0]] if order else 0
    return Presidential(
        order=order,
        needed=needed,
        leader_votes=leader_votes,
        leader_share=leader_votes / voted if voted else None,
        majority=voted > 0 and leader_votes >= needed,
        runoff=len(votes) == 2,
    )


def contest_rules(rnd: Round) -> dict:
    rules = dict(DEFAULTS.get(rnd.kind, {}))
    rules.update({k: v for k, v in (rnd.contest or {}).items() if v is not None})
    return rules


def evaluate(rnd: Round) -> tuple[Totals, Proportional | Presidential | None]:
    n = len(rnd.contestants)
    t = totals(rnd.stations, n)
    rules = contest_rules(rnd)
    if rnd.kind == "presidential":
        return t, presidential(t.votes, t.ballots or t.voted)  # RIK counts "voters who voted" as ballots in the box
    if rnd.kind in ("parliamentary", "provincial", "local") and rules.get("seats"):
        seats = int(rules["seats"])
        return t, proportional(
            t.votes, t.voted, [c.minority for c in rnd.contestants], seats=seats,
            threshold=rules.get("threshold", 0.03), minority_factor=rules.get("minority_factor", 1.35),
            majority=rules.get("majority") or seats // 2 + 1, two_thirds=rules.get("two_thirds"),
        )
    return t, None
