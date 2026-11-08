"""The home page's cards: one rule each, the same for every list, and nothing guessed where data is missing."""

from izbori import highlights as H
from izbori.model import Contestant


class P:
    def __init__(self, code, rounds, keys):
        self.code, self.rounds = code, rounds
        self.stations = {r: type("S", (), {"key": k})() for r, k in zip(rounds, keys)}


def muns():
    return [{"code": "1", "name": "A", "kind": "domestic", "stations": 20, "counted": 20, "flagged": 5},
            {"code": "2", "name": "B", "kind": "domestic", "stations": 10, "counted": 10, "flagged": 4},
            {"code": "3", "name": "C", "kind": "domestic", "stations": 5, "counted": 5, "flagged": 5},  # too small
            {"code": "4", "name": "D", "kind": "abroad", "stations": 30, "counted": 30, "flagged": 30},
            {"code": "5", "name": "E", "kind": "domestic", "stations": 12, "counted": 12, "flagged": 0}]


def test_gap_picks_the_largest_difference_and_skips_missing_classes():
    rows = [{"number": 1, "label": "One", "votes": {"size": [0.5, 0.4, 0.3, 0.2, 0.1]}},
            {"number": 2, "label": "Two", "votes": {"size": [0.1, 0.2, 0.3, 0.4, 0.6]}},
            {"number": 3, "label": "Three", "votes": {"size": [0.9, None, None, None, None]}}]
    g = H.gap(rows)
    assert (g["number"], g["small"], g["large"]) == (2, 0.1, 0.6) and abs(g["diff"] - 0.5) < 1e-12
    assert H.gap([]) is None


def test_flagged_ranks_by_share_in_the_country_with_enough_stations():
    assert [m["name"] for m in H.flagged(muns())] == ["B", "A"]


def test_repeated_counts_places_flagged_in_every_election_they_took_part_in():
    flagged = {"r1": {"1/1", "1/2"}, "r2": {"1/1", "1/2"}, "r3": {"1/1"}}
    places = [P("1", ["r3", "r2", "r1"], ["1/1", "1/1", "1/1"]),  # three elections, flagged in all
              P("1", ["r3", "r2", "r1"], ["1/2", "1/2", "1/2"]),  # not in r3
              P("2", ["r2", "r1"], ["1/1", "1/1"])]  # only two elections
    r = H.repeated(places, flagged, {"1": "A"})
    assert r == {"n": 1, "elections": 3, "municipalities": [{"code": "1", "name": "A", "n": 1}]}
    assert H.repeated(places, {"r1": set(), "r2": set(), "r3": set()}, {}) is None


def test_top_three_with_their_best_and_worst_municipality_and_the_same_rule_when_swapped():
    cs = [Contestant(number=i + 1, name=f"L{i + 1}", short="") for i in range(4)]
    votes = {"1": [100, 50, 10, 1], "2": [20, 60, 5, 1], "5": [30, 30, 40, 1], "3": [0, 0, 0, 9], "4": [0, 0, 0, 9]}
    out = H.top(cs, [c.name for c in cs], muns(), votes)
    assert [o["number"] for o in out] == [1, 2, 3]  # by votes in the country; C and D (small, abroad) don't count
    assert (out[0]["best"]["name"], out[0]["worst"]["name"]) == ("A", "B")
    swapped = {k: [v[1], v[0], v[2], v[3]] for k, v in votes.items()}
    out2 = H.top(cs, [c.name for c in cs], muns(), swapped)
    assert [o["number"] for o in out2] == [2, 1, 3]
    assert (out2[0]["best"], out2[0]["worst"]) == (out[0]["best"], out[0]["worst"])
    assert H.top(cs[:2], ["a", "b"], muns(), votes) == []  # fewer than three contestants: no card
