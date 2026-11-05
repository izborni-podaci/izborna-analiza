"""Loader, election math and station checks, against the final 2026 parliamentary file."""

from izbori.checks import group_by_station, station_flags
from izbori.contests import evaluate, presidential, proportional
from izbori.load import parse
from izbori.translit import latin

# Stations from the manual review of 2 November 2026 (municipality as RIK writes it, station number).
REVIEWED = [
    ("Дољевац", "24"), ("Дољевац", "25"), ("Дољевац", "23"), ("Дољевац", "12"), ("Град Кикинда", "60"),
    ("Штрпце", "3"), ("Град Нови Пазар", "46"), ("Град Нови Пазар", "47"), ("Град Нови Пазар", "41"),
    ("Босилеград", "21"), ("Владичин Хан", "41"), ("Дољевац", "22"), ("Трговиште", "24"), ("Трговиште", "23"),
    ("Трговиште", "21"), ("Босилеград", "16"), ("Неготин", "48"), ("Трговиште", "16"), ("Град Врање", "106"),
    ("Град Лесковац", "117"), ("Трговиште", "25"), ("Бујановац", "43"), ("Трговиште", "19"), ("Дољевац", "27"),
]
TYPOS = {("Град Смедерево", "52"), ("Бујановац", "52"), ("Брус", "13"), ("Пријепоље", "35"), ("Босилеград", "21")}


def _find(rnd, municipality, number):
    return next(s for s in rnd.stations if s.municipality == municipality and s.number == number)


def test_latin():
    assert latin("Љубовија") == "Ljubovija"
    assert latin("ЉУБОВИЈА") == "LJUBOVIJA"
    assert latin("КОЊ") == "KONJ"
    assert latin("Њ") == "Nj"
    assert latin("Џеп и ђак") == "Džep i đak"
    assert latin("RIK 2026") == "RIK 2026"
    # two-letter capitals follow the next letter, or at the end of a word the one before
    assert latin("ЉИ Љи АЉ аЉ Љ.") == "LJI Lji ALJ aLj Lj."
    assert latin("ЏАК Џак ЊЕГОШ") == "DŽAK Džak NJEGOŠ"
    assert latin("ᲂ") == "o"  # an old form of о
    assert latin("<p title=\"Ђак\">Ђурђевак</p>") == "<p title=\"Đak\">Đurđevak</p>"


def test_parse_counts_contestants(raw2026):
    stations, n = parse(raw2026)
    assert len(stations) == 8392
    assert n == 18  # 30 columns in the file, the last 12 always zero
    assert all(len(s.votes) == 18 for s in stations)
    assert len({s.key for s in stations}) == 8392


def test_station_fields(round2026):
    s = _find(round2026, "Градска општина Барајево", "1")
    assert (s.registered, s.voted, s.ballots, s.valid, s.invalid) == (607, 419, 419, 415, 4)
    assert s.minutes_url.startswith("https://rik.parlament.gov.rs/")
    assert s.minutes_uploaded is not None
    assert s.kind == "domestic"
    assert _find(round2026, "Иностранство", "1").kind == "abroad"


def test_seats_2026(round2026):
    totals, result = evaluate(round2026)
    assert totals.voted == 4_444_310
    assert totals.registered == 6_451_292
    assert result.threshold_votes == 133_330
    seats = {round2026.contestants[r.index].short: r.seats for r in result.lists if r.seats}
    assert seats == {"Studentska lista": 140, "Ujedinjena Srbija": 103, "SVM": 2, "Albanska koalicija": 2,
                     "SDA Sandžaka": 1, "SPP (Zukorlić)": 1, "Ljudski (Ljajić)": 1}
    assert sum(seats.values()) == 250
    by_short = {round2026.contestants[r.index].short: r for r in result.lists}
    assert by_short["SPP (Zukorlić)"].keep == 71
    assert by_short["Ujedinjena Srbija"].keep == 11_429


def test_proportional_minority_factor():
    # 100 seats; list 3 is a minority list under the threshold and takes part with votes x1.35
    r = proportional([6000, 3700, 200, 100], voted=10_000, minority=[False, False, True, False], seats=100)
    assert [x.takes_part for x in r.lists] == [True, True, True, False]
    assert r.lists[2].factor == 1.35
    assert sum(x.seats for x in r.lists) == 100
    assert r.lists[2].seats == 2


def test_presidential_majority_of_voters():
    # 1,000 voted including 50 invalid: the leader needs 501, so 500 isn't enough
    p = presidential([500, 300, 150], voted=1000)
    assert p.needed == 501 and not p.majority and p.short_by == 1 and not p.runoff
    assert presidential([501, 300, 150], voted=1000).majority
    assert presidential([400, 350], voted=760).runoff


def test_reviewed_stations_are_flagged(round2026):
    flagged = group_by_station(station_flags(round2026))
    for municipality, number in REVIEWED:
        s = _find(round2026, municipality, number)
        assert s.key in flagged, (municipality, number)


def test_typing_errors(round2026):
    flags = station_flags(round2026)
    found = set()
    by_key = {s.key: s for s in round2026.stations}
    for f in flags:
        if f.code == "full_turnout_typo":
            s = by_key[f.station]
            found.add((s.municipality, s.number))
    assert found == TYPOS


def test_specific_findings(round2026):
    flags = group_by_station(station_flags(round2026))

    def codes(m, n):
        return {f.code for f in flags.get(_find(round2026, m, n).key, [])}

    assert "correction_still_odd" in codes("Босилеград", "21")
    assert "invalid_spike" in codes("Штрпце", "3")
    for number, diff in (("23", 17), ("24", 12)):
        f = next(f for f in flags[_find(round2026, "Дољевац", number).key] if f.code == "signed_over_ballots")
        assert f.data["diff"] == diff


def test_checks_ignore_who_leads(round2026):
    """Swapping two contestants' votes everywhere must not change which stations are flagged."""
    import copy
    swapped = copy.deepcopy(round2026)
    for s in swapped.stations:
        s.votes[0], s.votes[2] = s.votes[2], s.votes[0]
    before = {(f.station, f.code) for f in station_flags(round2026)}
    after = {(f.station, f.code) for f in station_flags(swapped)}
    assert before == after


def test_identical_results(round2026):
    """Two stations of one municipality with the same votes for every list are flagged, each naming the other;
    the same votes in another municipality, too few votes or too few lists with votes are not. The real file has
    no such pair."""
    import copy
    from izbori.describe import describe
    assert not any(f.code == "identical_results" for f in station_flags(round2026))
    rnd = copy.deepcopy(round2026)
    domestic = [s for s in rnd.stations if s.counted and s.kind == "domestic" and (s.valid or 0) >= 100]
    a = domestic[0]
    b = next(s for s in domestic if s.municipality_code == a.municipality_code and s is not a)
    other = next(s for s in domestic if s.municipality_code != a.municipality_code)
    b.votes = list(a.votes)
    other.votes = list(a.votes)
    found = {f.station: f for f in station_flags(rnd) if f.code == "identical_results"}
    assert set(found) == {a.key, b.key}
    assert found[a.key].data["twins"] == [b.number] and found[b.key].data["twins"] == [a.number]
    assert b.number in describe(found[a.key], "en")
    # every contestant is treated alike: swapping two lists everywhere changes nothing
    swapped = copy.deepcopy(rnd)
    for s in swapped.stations:
        s.votes[0], s.votes[2] = s.votes[2], s.votes[0]
    assert {f.station for f in station_flags(swapped) if f.code == "identical_results"} == set(found)
    # two lists with votes, or fewer than 50 votes, match by chance too easily
    n = len(a.votes)
    for votes in ([60, 40] + [0] * (n - 2), [20, 10, 5] + [0] * (n - 3)):
        a.votes, b.votes = list(votes), list(votes)
        assert not any(f.code == "identical_results" for f in station_flags(rnd))


def test_several_minutes_links(round2026):
    s = next(x for x in round2026.stations if x.key == "70157/25")
    assert len(s.minutes_links) == 3
    assert all(url.startswith("https://") and "\n" not in url for _, url in s.minutes_links)
    assert s.minutes_url == s.minutes_links[-1][1]


def test_latin_handles_other_cyrillic_letters():
    from izbori.translit import has_cyrillic, latin
    assert latin("БУЛЕВАР КРАЉА ПЕТРА І") == "BULEVAR KRALJA PETRA I"
    assert not has_cyrillic(latin("Київ, Їжак, Ёлка, Объект"))
