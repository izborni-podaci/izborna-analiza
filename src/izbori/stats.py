"""Statistics for a whole round. Weak signals, shown with their limits and never as station flags.
Computed for the two contestants with the most votes, whoever they are."""

from __future__ import annotations

import math
from dataclasses import dataclass

from izbori.model import Round


def _gser(a: float, x: float) -> float:
    ap, total, delta = a, 1.0 / a, 1.0 / a
    for _ in range(1000):
        ap += 1
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * 1e-14:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a: float, x: float) -> float:
    tiny = 1e-300
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-14:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_p(chi2: float, df: int) -> float:
    """Chance of a chi-square value at least this large with `df` degrees of freedom."""
    a, x = df / 2, chi2 / 2
    if x <= 0:
        return 1.0
    return 1 - _gser(a, x) if x < a + 1 else _gcf(a, x)


@dataclass
class Digits:
    contestant: int
    counts: list[int]
    n: int
    chi2: float
    p: float


@dataclass
class RoundShare:
    measure: str  # "turnout" or a contestant index
    stations: int
    hits: int

    @property
    def share(self) -> float | None:
        return self.hits / self.stations if self.stations else None


def top_two(votes: list[int]) -> list[int]:
    return sorted(range(len(votes)), key=lambda i: -votes[i])[:2]


def last_digits(rnd: Round, idx: int, minimum: int = 100) -> Digits | None:
    values = [s.votes[idx] for s in rnd.stations if s.counted and s.kind == "domestic"
              and (s.votes[idx] or 0) >= minimum]
    if len(values) < 50:
        return None
    counts = [0] * 10
    for v in values:
        counts[v % 10] += 1
    n = len(values)
    chi2 = sum((c - n / 10) ** 2 / (n / 10) for c in counts)
    return Digits(contestant=idx, counts=counts, n=n, chi2=chi2, p=chi2_p(chi2, 9))


def round_percentages(rnd: Round, idxs: list[int], window: float = 0.05, min_registered: int = 500) -> list[RoundShare]:
    rows = [s for s in rnd.stations if s.counted and s.kind == "domestic" and s.registered >= min_registered
            and s.valid]

    def near(x: float) -> bool:
        return abs(100 * x - round(100 * x)) < window

    out = [RoundShare("turnout", len(rows), sum(1 for s in rows if near(s.voted / s.registered)))]
    for i in idxs:
        out.append(RoundShare(str(i), len(rows), sum(1 for s in rows if near((s.votes[i] or 0) / s.valid))))
    return out


def correlation(rnd: Round, idx: int, min_registered: int = 100) -> float | None:
    rows = [s for s in rnd.stations if s.counted and s.kind == "domestic" and s.registered >= min_registered
            and s.valid]
    if len(rows) < 3:
        return None
    xs = [s.voted / s.registered for s in rows]
    ys = [(s.votes[idx] or 0) / s.valid for s in rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else None


def turnout_histogram(rnd: Round, min_registered: int = 100) -> list[int]:
    bins = [0] * 101
    for s in rnd.stations:
        if s.counted and s.kind == "domestic" and s.registered >= min_registered:
            bins[min(100, int(100 * s.voted / s.registered))] += 1
    return bins


@dataclass
class RegisterChange:
    code: str
    name: str
    before: int
    now: int

    @property
    def change(self) -> float:
        return self.now / self.before - 1 if self.before else 0.0


def register_changes(rnd: Round, prev: Round, min_registered: int = 1000) -> tuple[float, list[RegisterChange]]:
    """Registered voters per municipality now and at the previous election; national change first."""
    def totals(r: Round) -> dict[str, list]:
        out: dict[str, list] = {}
        for s in r.stations:
            if s.counted and s.kind == "domestic":
                row = out.setdefault(s.municipality_code, [s.municipality, 0])
                row[1] += s.registered
        return out
    a, b = totals(rnd), totals(prev)
    rows = [RegisterChange(code, a[code][0], b[code][1], a[code][1]) for code in a if code in b
            and max(a[code][1], b[code][1]) >= min_registered]
    nat_before = sum(r.before for r in rows)
    national = sum(r.now for r in rows) / nat_before - 1 if nat_before else 0.0
    rows.sort(key=lambda r: -abs(r.change - national))
    return national, rows
