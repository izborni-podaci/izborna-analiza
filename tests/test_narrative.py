"""The sentences at the top of the pages across elections."""

from izbori.narrative import Election, municipality, place, short_label
from izbori.translit import latin


def lat(summary) -> list[tuple[str, list[str]]]:
    return [(latin(r.label), [latin(x) for x in r.lines]) for r in summary.rows]


def rows() -> list[Election]:
    """A station in three elections, newest first, renumbered from 10 to 14."""
    return [
        Election("Parlamentarni 2026", registered=1321, turnout=0.704, invalid=0.0054, flags=["turnout_drop"],
                 leader="Листа А", leader_share=0.718, ref_turnout=0.695, ref_invalid=0.009, ref_leader_share=0.607,
                 same_leader=True, number="14", name="ЗЕМУНСКА ГИМНАЗИЈА"),
        Election("Lokalni 2024", registered=1379, turnout=0.476, invalid=0.012, flags=[], leader="Листа Б",
                 leader_share=0.478, ref_turnout=0.48, ref_invalid=0.010, ref_leader_share=0.5, same_leader=False,
                 number="14", name="ЗЕМУНСКА ГИМНАЗИЈА"),
        Election("Parlamentarni 2023", registered=1492, turnout=0.597, invalid=0.008, flags=["invalid_spike", "turnout_drop"],
                 leader="Листа В", leader_share=0.421, ref_turnout=0.6, ref_invalid=0.008, ref_leader_share=0.4,
                 same_leader=True, number="10", name="Земунска гимназија"),
    ]


def test_place_in_the_asked_order():
    summary = place(rows(), ["Pokrajinski 2023"], "lat")
    assert latin(summary.context) == "Najnoviji izbori: Parlamentarni 2026 · poređenje sa opštinom"
    assert lat(summary) == [
        ("Upozorenja", ["Na 2 od 3 izbora: Parlamentarni 2026 (pad izlaznosti); Parlamentarni 2023 (mnogo nevažećih "
                    "listića, pad izlaznosti)",
                    "Isto upozorenje više puta: pad izlaznosti (na 2 izbora)",
                    "Nevažeći 0,5% (opština 0,9%) · veći nego u opštini na 1 od 3 izbora"]),
        ("Izlaznost", ["70,4% · 0,9 poena više nego u opštini", "Ranije 47,6–59,7%"]),
        ("Najviše glasova", ["Lista A 71,8% (opština 60,7%)", "Na 2 od 3 izbora prvi i u opštini"]),
        ("Mesto", ["Ranije BM 10 (Parlamentarni 2023)", "Upisanih 1.492 (Parlamentarni 2023) → 1.321, −11,5%",
                   "Nije glasalo na: Pokrajinski 2023"]),
    ]


def test_place_in_english():
    rows_en = {r.label: r.lines for r in place(rows(), [], "en").rows}
    assert rows_en["Flags"][0].startswith("In 2 of 3 elections: Parlamentarni 2026 (turnout drop);")
    assert rows_en["Flags"][2] == "Invalid ballots 0.5% (municipality 0.9%) · higher than in the municipality in 1 of 3 elections"
    assert rows_en["Turnout"] == ["70.4% · 0.9 points higher than in the municipality", "Earlier 47.6–59.7%"]
    assert rows_en["Most votes"] == ["Lista A 71.8% (municipality 60.7%)", "Also first in the municipality in 2 of 3 elections"]
    assert rows_en["The place"][0] == "Earlier No. 10 (Parlamentarni 2023)"


def test_place_variants():
    one = [rows()[0]]
    one[0].flags = []
    assert lat(place(one, [], "lat")) == [
        ("Upozorenja", ["Bez upozorenja", "Nevažeći 0,5% (opština 0,9%)"]),
        ("Izlaznost", ["70,4% · 0,9 poena više nego u opštini"]),  # nothing earlier
        ("Najviše glasova", ["Lista A 71,8% (opština 60,7%)"]),
    ]  # one election: nothing changed, and it missed none

    same = rows()[:2]
    same[0].ref_turnout = 0.7041  # equal once rounded as the page shows it
    same[1].turnout, same[1].invalid = 0.5, 0.009
    got = dict(lat(place(same, [], "lat")))
    assert got["Izlaznost"] == ["70,4% · koliko i u opštini", "Ranije 50,0% (Lokalni 2024)"]
    assert got["Upozorenja"][-1].endswith("nikad veći nego u opštini")
    assert got["Mesto"][0] == "Isti broj i naziv na svim izborima"

    # the latest election has no count yet: the figures name the one they come from
    late = rows()
    late[0].turnout = late[0].invalid = None
    got = dict(lat(place(late, [], "lat")))
    assert got["Izlaznost"][0].startswith("47,6% (Lokalni 2024)")


def test_place_names_that_really_changed():
    r = rows()
    r[1].name = 'ОШ „ИВАН ГОРАН КОВАЧИЋ“-3'
    r[0].name = 'ОШ "ИВАН ГОРАН КОВАЧИЋ" - 3'  # the same name, written differently
    r[2].name = "МК АРНАЈЕВО"
    got = dict(lat(place(r, [], "lat")))
    assert got["Mesto"][:2] == ["Ranije BM 10 (Parlamentarni 2023)", "Ranije naziv MK ARNAJEVO (Parlamentarni 2023)"]


def test_observers_records():
    r = rows()
    r[0].observers, r[1].observers, r[2].observers = True, False, True
    assert dict(lat(place(r, [], "lat")))["Zapisnici"] == ["O posmatračima za 2 od 3 izbora · bez: Lokalni 2024"]
    one = [rows()[0]]
    one[0].observers = False
    assert dict(lat(place(one, [], "lat")))["Zapisnici"] == ["Zapisnik o posmatračima nije objavljen"]


def test_short_label_same_rule_for_everyone():
    assert short_label("Студентска листа") == "Студентска листа"
    assert short_label("СРБИЈА ПРОТИВ НАСИЉА – МИРОСЛАВ МИКИ АЛЕКСИЋ - МАРИНИКА ТЕПИЋ (СТРАНКА СЛОБОДЕ И ПРАВДЕ)") == \
        "СРБИЈА ПРОТИВ НАСИЉА – МИРОСЛАВ МИКИ АЛЕКСИЋ…"
    assert short_label("Ivica Dačić – Faktor stabilnosti (SPS)") == "Ivica Dačić – Faktor stabilnosti"


def test_municipality():
    r = rows()
    for e, (stations, flagged, overall) in zip(r, [(221, 7, 0.026), (212, 12, 0.03), (207, 27, 0.04)]):
        e.stations, e.flagged, e.ref_flagged, e.flags = stations, flagged, overall, []
    summary = municipality(r, ["Lokalni 2024"], (46, 14), (17, 8, 0), "lat")
    assert latin(summary.context) == "Najnoviji izbori: Parlamentarni 2026 · poređenje sa celim izborima"
    got = dict(lat(summary))
    assert got["Upozorenja"] == ["7 od 221 biračkih mesta za proveru (3,2%; ukupno 2,6%)",
                             "Mesta sa upozorenjem na bar jednim izborima: 46 · na bar dvoje: 14",
                             "Nevažeći 0,5% (ukupno 0,9%) · veći nego na celim izborima na 1 od 3 izbora"]
    assert got["Izlaznost"][0] == "70,4% · 0,9 poena više nego na celim izborima"
    assert got["Najviše glasova"][1] == "Na 2 od 3 izbora prvi i na celim izborima"
    assert got["Biračka mesta"] == ["207 (Parlamentarni 2023) → 221 · novih 17 · ne koristi se 8",  # no "renumbered 0"
                                    "Upisanih 1.492 (Parlamentarni 2023) → 1.321, −11,5%",
                                    "Opština nije glasala na: Lokalni 2024"]


def test_rank_among_peers():
    r = rows()
    r[0].rank_invalid, r[0].rank_turnout = (12, 221), (3, 221)
    got = dict(lat(place(r, [], "lat")))
    assert got["Upozorenja"][-1] == "Nevažeći 0,5% (opština 0,9%) · 12. od 221 u opštini · veći nego u opštini na 1 od 3 izbora"
    assert got["Izlaznost"][1] == "3. od 221 u opštini · ranije 47,6–59,7%"
    en = {x.label: x.lines for x in place(r, [], "en").rows}
    assert en["Turnout"][1] == "3 of 221 in the municipality · earlier 47.6–59.7%"
    r[0].rank_invalid = None  # too few stations to rank
    assert "12. od 221" not in " ".join(dict(lat(place(r, [], "lat")))["Upozorenja"])


def test_rank_helper():
    from izbori.site import rank_of
    values = sorted([0.01, 0.02, 0.02, 0.03, 0.05, 0.08])
    assert rank_of(0.08, values) == (1, 6)
    assert rank_of(0.02, values) == (4, 6)  # tied with another, both fourth
    assert rank_of(0.01, values) == (6, 6)
    assert rank_of(0.02, values[:4]) is None  # fewer than five
