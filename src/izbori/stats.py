"""Statistics for a whole round and for each municipality. Weak signals, shown with their limits and never as
station flags. Computed for the two contestants with the most votes, whoever they are, or for every contestant."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from izbori.model import Round, Station


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


def poisson_at_least(k: int, mean: float) -> float:
    """Chance of at least k events when `mean` are expected (Poisson). For a sum of chances it is a little cautious:
    its spread is never smaller than the sum's."""
    if k <= 0:
        return 1.0
    if mean <= 0:
        return 0.0
    return _gser(k, mean) if mean < k + 1 else 1 - _gcf(k, mean)


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
    expected: float = 0.0  # stations expected near a whole percent by chance, given each one's denominator

    @property
    def share(self) -> float | None:
        return self.hits / self.stations if self.stations else None

    @property
    def p(self) -> float:
        return poisson_at_least(self.hits, self.expected)


@dataclass
class LocalTest:
    """One municipality's test. `adjusted` is p times the number of municipalities tested (Bonferroni), at most 1:
    among so many tests, some p comes out small by chance."""
    code: str
    name: str
    n: int  # station measures (round percentages) or vote counts (last digits)
    observed: float  # stations near a whole percent, or the chi-square value
    expected: float  # stations expected near a whole percent; 0 for last digits
    p: float
    adjusted: float = 1.0


def _bonferroni(tests: list[LocalTest]) -> tuple[int, list[LocalTest]]:
    m = len(tests)
    for x in tests:
        x.adjusted = min(1.0, x.p * m)
    tests.sort(key=lambda x: (x.adjusted, x.p, x.code))
    return m, tests


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


WHOLE_WINDOW = Fraction(1, 20)  # within 0.05 points of a whole percent
WHOLE_MIN_COUNT = 10  # counts this close to none or to all are left out: near the ends, counts aren't spread evenly


def near_whole(k: int, d: int, window: Fraction = WHOLE_WINDOW) -> bool:
    """Is k/d within `window` points of a whole percent? Exact, in integers."""
    whole = (200 * k + d) // (2 * d)
    return abs(100 * k - whole * d) < window * d


@lru_cache(maxsize=None)
def whole_chance(d: int, window: Fraction = WHOLE_WINDOW) -> float:
    """The chance that a count out of d lands near a whole percent, if every count close by is as likely. It depends
    on d: of 500 valid votes every fifth count is a whole percent, of 737 about every tenth."""
    lo_k, hi_k = WHOLE_MIN_COUNT, d - WHOLE_MIN_COUNT
    if hi_k < lo_k:
        return 0.0
    num, den = window.numerator, window.denominator
    step, reach, total = 100 * den, num * d, 0
    for whole in range(101):  # counts k with |100k - whole*d| < window*d
        centre = whole * d * den
        lo = max((centre - reach) // step + 1, lo_k)
        hi = min(-(-(centre + reach) // step) - 1, hi_k)
        total += max(0, hi - lo + 1)
    return total / (hi_k - lo_k + 1)


def _whole_measures(idxs: list[int]):
    yield "turnout", lambda s: (s.voted, s.registered)
    for i in idxs:
        yield str(i), lambda s, i=i: (s.votes[i] or 0, s.valid)


def _whole_rows(rnd: Round, min_registered: int) -> list[Station]:
    return [s for s in rnd.stations if s.counted and s.kind == "domestic" and s.registered >= min_registered
            and s.valid]


def _whole_counts(k: int, d: int) -> bool:
    return WHOLE_MIN_COUNT <= k <= d - WHOLE_MIN_COUNT


def round_percentages(rnd: Round, idxs: list[int], min_registered: int = 100) -> list[RoundShare]:
    """Stations where turnout or a share lands near a whole percent, against the number expected by chance."""
    rows = _whole_rows(rnd, min_registered)
    out = []
    for measure, get in _whole_measures(idxs):
        n = hits = 0
        expected = 0.0
        for s in rows:
            k, d = get(s)
            if _whole_counts(k, d):
                n += 1
                hits += near_whole(k, d)
                expected += whole_chance(d)
        out.append(RoundShare(measure, n, hits, expected))
    return out


def round_percentages_by_municipality(rnd: Round, idxs: list[int], min_registered: int = 100,
                                      min_expected: float = 5.0) -> tuple[int, list[LocalTest]]:
    """The same test for each municipality, turnout and the shares pooled; those expecting fewer than
    `min_expected` hits are not tested."""
    acc: dict[str, list] = {}
    for s in _whole_rows(rnd, min_registered):
        row = acc.setdefault(s.municipality_code, [s.municipality, 0, 0, 0.0])
        for _, get in _whole_measures(idxs):
            k, d = get(s)
            if _whole_counts(k, d):
                row[1] += 1
                row[2] += near_whole(k, d)
                row[3] += whole_chance(d)
    return _bonferroni([LocalTest(code, name, n, hits, expected, poisson_at_least(hits, expected))
                        for code, (name, n, hits, expected) in acc.items() if expected >= min_expected])


def last_digits_by_municipality(rnd: Round, minimum: int = 100, min_counts: int = 50) -> tuple[int, list[LocalTest]]:
    """Last digits of every contestant's vote counts of at least `minimum`, pooled per municipality; tested where
    there are at least `min_counts` of them (five expected per digit)."""
    values: dict[str, list[int]] = defaultdict(list)
    names: dict[str, str] = {}
    for s in rnd.stations:
        if s.counted and s.kind == "domestic":
            names[s.municipality_code] = s.municipality
            values[s.municipality_code].extend(v for v in s.votes if v is not None and v >= minimum)
    tests = []
    for code, vals in values.items():
        n = len(vals)
        if n >= min_counts:
            counts = [0] * 10
            for v in vals:
                counts[v % 10] += 1
            chi2 = sum((c - n / 10) ** 2 / (n / 10) for c in counts)
            tests.append(LocalTest(code, names[code], n, chi2, 0.0, chi2_p(chi2, 9)))
    return _bonferroni(tests)


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
