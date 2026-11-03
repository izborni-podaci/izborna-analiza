"""The sentences at the top of the pages across elections."""

from izbori.narrative import Election, municipality, place, short_label
from izbori.translit import latin


def lat(paragraphs: list[str]) -> list[str]:
    return [latin(p) for p in paragraphs]


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
    text = lat(place(rows(), ["Pokrajinski 2023"], "lat"))
    assert text == [
        "Provere su dale oznaku na 2 od 3 izbora: Parlamentarni 2026 (pad izlaznosti); Parlamentarni 2023 "
        "(mnogo nevažećih listića, pad izlaznosti). Ista oznaka više puta: pad izlaznosti (na 2 izbora). "
        "Udeo nevažećih listića bio je veći nego u opštini na 1 od 3 izbora; najveći je bio 1,2% "
        "(Lokalni 2024; opština 1,0%).",
        "Izlaznost: 70,4% (Parlamentarni 2026), 0,9 poena više nego u opštini; na ranijim izborima od 47,6% do "
        "59,7%. Upisanih birača: 1.492 (Parlamentarni 2023) → 1.321 (Parlamentarni 2026), −11,5%.",
        "Najviše glasova (Parlamentarni 2026): Lista A, 71,8% (opština 60,7%); na 2 od 3 izbora prvi ovde bio "
        "je prvi i u opštini.",
        "Broj mesta ranije je bio 10 (Parlamentarni 2023). Nije glasalo na: Pokrajinski 2023.",
    ]


def test_place_in_english():
    text = place(rows(), [], "en")
    assert text[0].startswith("Checks flagged it in 2 of 3 elections: Parlamentarni 2026 (turnout drop);")
    assert "the highest was 1.2% (Lokalni 2024; municipality 1.0%)" in text[0]
    assert text[1].startswith("Turnout: 70.4% (Parlamentarni 2026), 0.9 points higher than in the municipality")
    assert text[2] == ("Most votes (Parlamentarni 2026): Lista A, 71.8% (municipality 60.7%); in 2 of 3 elections, "
                       "whoever led here also led in the municipality.")
    assert text[3] == "Its number used to be 10 (Parlamentarni 2023)."


def test_place_variants():
    one = [rows()[0]]
    one[0].flags = []
    text = lat(place(one, [], "lat"))
    assert text[0] == ("Nijedna provera nije dala oznaku ni na jednim izborima na kojima je mesto glasalo. "
                       "Udeo nevažećih listića: 0,5% (Parlamentarni 2026; opština 0,9%).")
    assert text[1] == "Izlaznost: 70,4% (Parlamentarni 2026), 0,9 poena više nego u opštini."  # nothing earlier
    assert text[2] == "Najviše glasova (Parlamentarni 2026): Lista A, 71,8% (opština 60,7%)."
    assert len(text) == 3  # one election: nothing changed, and it missed none

    same = rows()[:2]
    same[0].ref_turnout = 0.7041  # equal once rounded as the page shows it
    same[1].turnout, same[1].invalid = 0.5, 0.009
    text = lat(place(same, [], "lat"))
    assert "Izlaznost: 70,4% (Parlamentarni 2026), koliko i u opštini; na ranijim izborima 50,0% (Lokalni 2024)." in text[1]
    assert "Udeo nevažećih listića ni na jednim izborima nije bio veći nego u opštini" in text[0]
    assert text[-1] == "Broj i naziv mesta isti su na svim izborima na kojima je glasalo."


def test_place_names_that_really_changed():
    r = rows()
    r[1].name = 'ОШ „ИВАН ГОРАН КОВАЧИЋ“-3'
    r[0].name = 'ОШ "ИВАН ГОРАН КОВАЧИЋ" - 3'  # the same name, written differently
    r[2].name = "МК АРНАЈЕВО"
    text = lat(place(r, [], "lat"))
    assert text[-1] == "Broj mesta ranije je bio 10 (Parlamentarni 2023). Naziv je ranije bio MK ARNAJEVO (Parlamentarni 2023)."


def test_short_label_same_rule_for_everyone():
    assert short_label("Студентска листа") == "Студентска листа"
    assert short_label("СРБИЈА ПРОТИВ НАСИЉА – МИРОСЛАВ МИКИ АЛЕКСИЋ - МАРИНИКА ТЕПИЋ (СТРАНКА СЛОБОДЕ И ПРАВДЕ)") == \
        "СРБИЈА ПРОТИВ НАСИЉА – МИРОСЛАВ МИКИ АЛЕКСИЋ…"
    assert short_label("Ivica Dačić – Faktor stabilnosti (SPS)") == "Ivica Dačić – Faktor stabilnosti"


def test_municipality():
    r = rows()
    for e, (stations, flagged, overall) in zip(r, [(221, 7, 0.026), (212, 12, 0.03), (207, 27, 0.04)]):
        e.stations, e.flagged, e.ref_flagged, e.flags = stations, flagged, overall, []
    text = lat(municipality(r, ["Lokalni 2024"], (46, 14), (17, 8, 0), "lat"))
    assert text[0].startswith("Biračkih mesta za proveru (Parlamentarni 2026): 7 od 221 (3,2%; ukupno 2,6%). "
                              "Mesta sa oznakom na bar jednim izborima: 46; na bar dvoje izbora: 14. "
                              "Udeo nevažećih listića bio je veći nego na celim izborima na 1 od 3 izbora;")
    assert text[1].startswith("Izlaznost: 70,4% (Parlamentarni 2026), 0,9 poena više nego na celim izborima;")
    assert text[2].endswith("na 2 od 3 izbora prvi ovde bio je prvi i na celim izborima.")
    assert text[3] == ("Biračkih mesta: 207 (Parlamentarni 2023) → 221 (Parlamentarni 2026); novih: 17, više se ne "
                       "koristi: 8. Opština nije glasala na: Lokalni 2024.")  # no "renumbered: 0"


def test_rank_among_peers():
    r = rows()
    r[0].rank_invalid, r[0].rank_turnout = (12, 221), (3, 221)
    text = lat(place(r, [], "lat"))
    assert text[0].endswith("Po udelu nevažećih listića (Parlamentarni 2026) mesto je 12. od 221 u opštini, "
                            "računajući od najvećeg.")
    assert "Po izlaznosti (Parlamentarni 2026) mesto je 3. od 221 u opštini, računajući od najveće." in text[1]
    en = place(r, [], "en")
    assert "By turnout (Parlamentarni 2026) it ranks 3 of 221 in the municipality, counting from the highest." in en[1]
    r[0].rank_invalid = None  # too few stations to rank
    assert "mesto je 12." not in lat(place(r, [], "lat"))[0]


def test_rank_helper():
    from izbori.site import rank_of
    values = sorted([0.01, 0.02, 0.02, 0.03, 0.05, 0.08])
    assert rank_of(0.08, values) == (1, 6)
    assert rank_of(0.02, values) == (4, 6)  # tied with another, both fourth
    assert rank_of(0.01, values) == (6, 6)
    assert rank_of(0.02, values[:4]) is None  # fewer than five
