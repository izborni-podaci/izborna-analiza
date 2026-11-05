"""Round-wide and per-municipality statistics: their arithmetic, and that they find what is planted in real data."""

import copy
import math

from izbori import stats


def test_chances():
    assert abs(stats.chi2_p(16.919, 9) - 0.05) < 1e-3
    assert stats.poisson_at_least(0, 3.0) == 1.0
    for k, mean in ((1, 1.0), (5, 2.5), (12, 8.0), (30, 31.0)):
        direct = 1 - sum(math.exp(-mean) * mean ** j / math.factorial(j) for j in range(k))
        assert abs(stats.poisson_at_least(k, mean) - direct) < 1e-9


def test_whole_percent_chance():
    """The expected share of counts near a whole percent follows the denominator, exactly."""
    for d in (20, 21, 199, 200, 300, 500, 737, 1000, 2999):
        counts = range(stats.WHOLE_MIN_COUNT, d - stats.WHOLE_MIN_COUNT + 1)
        brute = sum(stats.near_whole(k, d) for k in counts) / len(counts)
        assert abs(stats.whole_chance(d) - brute) < 1e-12
    assert stats.near_whole(350, 500) and not stats.near_whole(351, 500)
    assert abs(stats.whole_chance(500) - 0.2) < 0.01 and abs(stats.whole_chance(737) - 0.1) < 0.01


def test_round_percentages_match_chance(round2026):
    """In the real file, stations near a whole percent stay close to the number expected by chance."""
    top2 = stats.top_two([sum(s.votes[i] or 0 for s in round2026.stations) for i in range(len(round2026.contestants))])
    for r in stats.round_percentages(round2026, top2):
        assert r.stations > 7000
        assert abs(r.hits - r.expected) < 4 * math.sqrt(r.expected)


def _municipality(rnd, size):
    stations = [s for s in rnd.stations if s.counted and s.kind == "domestic"]
    by = {}
    for s in stations:
        by.setdefault(s.municipality_code, []).append(s)
    return next(v for v in by.values() if len(v) >= size)


def test_planted_round_percentages_found(round2026):
    rnd = copy.deepcopy(round2026)
    planted = _municipality(rnd, 60)
    for s in planted:
        s.voted = round(s.registered * round(100 * s.voted / s.registered) / 100)
    n, rows = stats.round_percentages_by_municipality(rnd, [0, 1])
    assert n > 100
    assert rows[0].code == planted[0].municipality_code and rows[0].adjusted < 0.05
    assert rows[0].p * n >= rows[0].adjusted


def test_planted_last_digits_found(round2026):
    rnd = copy.deepcopy(round2026)
    planted = _municipality(rnd, 60)
    for s in planted:
        s.votes = [v - v % 5 if v and v >= 100 else v for v in s.votes]
    n, rows = stats.last_digits_by_municipality(rnd)
    assert n > 50
    assert rows[0].code == planted[0].municipality_code and rows[0].adjusted < 0.05
    assert all(r.n >= 50 for r in rows)
