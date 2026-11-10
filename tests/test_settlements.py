"""Each polling station's settlement in the 2022 census: the census's hierarchy, RIK's names, the rules in order."""

import json

import openpyxl
from openpyxl.styles import Alignment

from izbori import settlements as S
from izbori.model import Station
from izbori.places import follow

# a census table by settlement in the Office's layout: names in the first column, the hierarchy by indentation
ROWS = [
    ("РЕПУБЛИКА СРБИЈА", 0), ("Градска", 1), ("Остала", 1),
    ("Београдска област \n(Град Београд)", 2), ("Градска", 1),
    ("Врачар", 2), ("Градска", 1), ("Београд (Врачар)", 4),
    ("Палилула", 2), ("Градска", 1), ("Остала", 1), ("Београд (Палилула)", 4), ("Овча", 4),
    ("Младеновац", 2), ("Младеновац (варош)", 4), ("Младеновац (село)", 4), ("Међулужје", 4),
    ("Сремска област", 2), ("Стара Пазова", 2), ("Голубинци", 4), ("Нови Бановци", 4), ("Бановци", 4),
    ("Стара Пазова", 4), ("Стари Бановци", 4),
    ("Нишавска област", 2), ("Град Ниш", 2), ("Насеље Ниш", 3),
    ("Палилула", 3), ("Ниш (Палилула)", 4), ("Доња Врежина", 4),
    ("Пчињска област", 2), ("Град Врање", 2), ("Врање", 3), ("Врање", 4), ("Бунушевац", 4),
    ("Врањска Бања", 3), ("Врањска Бања", 4), ("Корбевац", 4),
]


def census_table(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Укупан број становника, по насељеним местима"])
    ws.append([None])
    for i, (name, indent) in enumerate(ROWS, start=3):
        ws.cell(row=i, column=1, value=name).alignment = Alignment(indent=indent)
        ws.cell(row=i, column=3, value=100)
    wb.save(path)
    return path


def st(number, name="", municipality="Стара Пазова", code="80357", district="Сремски управни округ"):
    return Station(key=f"{code}/{number}", uid=number, number=number, name=name, municipality=municipality,
                   municipality_code=code, district=district, district_code="RS", registered=100, voted=50,
                   ballots=50, valid=50, invalid=0, entered="", votes=[50])


def census(tmp_path):
    return S.Census(S.load_units(census_table(tmp_path / "naselja.xlsx")))


def test_the_census_hierarchy_follows_the_indentation(tmp_path):
    units = S.load_units(census_table(tmp_path / "naselja.xlsx"))
    assert [u.key for u in units] == ["Врачар", "Палилула", "Младеновац", "Стара Пазова", "Град Ниш: Палилула",
                                      "Град Врање: Врање", "Град Врање: Врањска Бања"]
    assert units[1].settlements == ["Београд (Палилула)", "Овча"]
    assert units[1].area.startswith("Београдска област")


def test_rik_names_find_the_census_municipality(tmp_path):
    c = census(tmp_path)
    assert c.unit("Градска општина Палилула (Београд)").key == "Палилула"
    assert c.unit("Градска општина Палилула (Ниш)").key == "Град Ниш: Палилула"
    assert c.unit("Ниш-Палилула").key == "Град Ниш: Палилула"  # the 2022 results' way
    assert c.unit("Палилула", "Град Београд").key == "Палилула"
    assert c.unit("Палилула") is None  # two of them and nothing to tell which
    assert c.unit("Приштина") is None  # no census in Kosovo and Metohija
    vranje = st("1", municipality="Град Врање", code="13757")
    assert [u.key for u in c.for_round([vranje])["13757"]] == ["Град Врање: Врање", "Град Врање: Врањска Бања"]
    banja = st("1", municipality="Врањска Бања", code="13870")
    got = c.for_round([vranje, banja])
    assert [u.key for u in got["13757"]] == ["Град Врање: Врање"]
    assert [u.key for u in got["13870"]] == ["Град Врање: Врањска Бања"]


def test_the_rules_in_order(tmp_path):
    c = census(tmp_path)
    stations = [
        st("1", "ОШ БРАНКО РАДИЧЕВИЋ"), st("2", "ДОМ КУЛТУРЕ"), st("3", "МЗ СТАРИ БАНОВЦИ"),
        st("4", "ОШ БОШКО ПАЛКОВЉЕВИЋ ПИНКИ"), st("5", "ОШ ДУШАН ЈЕРКОВИЋ"), st("6", "ОШ СВЕТИ САВА"),
        st("7", ""), st("8", "ОШ НИКОЛА ТЕСЛА"),
        st("1", "ОШ ВУК КАРАЏИЋ", "Градска општина Врачар", "70114", "Град Београд"),
        st("1", "ОШ ЂУРА ЈАКШИЋ", "Градска општина Палилула (Београд)", "70173", "Град Београд"),
        st("2", "ДОМ КУЛТУРЕ", "Градска општина Палилула (Београд)", "70173", "Град Београд"),
        st("1", "ОШ СВЕТИ САВА", "Градска општина Младеновац", "70165", "Град Београд"),
        st("1", "", "Приштина", "90000", "Косовски округ"),
    ]
    addresses = {
        "80357/1": "ОШ Бранко Радичевић, Нови Бановци, Петра Драпшина 2",  # the longest name, after the building
        "80357/2": "Дом културе Голубинци",  # in the first part
        "80357/4": "OŠ Boško Palkovljević Pinki, Stara Pazova, Kralja Petra I 12",  # Latin
        "80357/5": "МЗ Стари Бановци, Дунавска 1",  # names another building than the results: not used
        "80357/6": "ОШ Свети Сава, Светосавска 16",  # a street and a number, no place: the seat
        "80357/8": "ОШ Никола Тесла",  # no street, no place: unknown
        "70173/1": "ОШ Ђура Јакшић, Београд, Рузвелтова 31",  # "Београд" is this municipality's "Београд (Палилула)"
        "70173/2": "Дом културе, Овча",
        "70165/1": "ОШ Свети Сава, Младеновац, Краља Петра 2",  # the town, not the village of the same name
    }
    got = S.join(stations, c, addresses)
    assert got["80357/1"] == {"u": "Стара Пазова", "s": "Нови Бановци", "m": "address"}
    assert got["80357/2"] == {"u": "Стара Пазова", "s": "Голубинци", "m": "building"}
    assert got["80357/3"] == {"u": "Стара Пазова", "s": "Стари Бановци", "m": "station"}
    assert got["80357/4"]["s"] == "Стара Пазова" and got["80357/4"]["m"] == "address"
    assert "80357/5" not in got  # the contradicting address is dropped and nothing else names the place
    assert got["80357/6"] == {"u": "Стара Пазова", "s": "Стара Пазова", "m": "seat"}
    assert "80357/7" not in got and "80357/8" not in got  # unknown is not zero
    assert got["70114/1"] == {"u": "Врачар", "s": "Београд (Врачар)", "m": "single"}
    assert got["70173/1"] == {"u": "Палилула", "s": "Београд (Палилула)", "m": "address"}
    assert got["70173/2"]["s"] == "Овча"
    assert got["70165/1"]["s"] == "Младеновац (варош)"
    assert "90000/1" not in got
    counts = S.summary(stations, got, c.for_round(stations))
    assert counts["no census"] == 1 and counts["none"] == 3


def test_a_manual_correction_comes_first(tmp_path):
    c = census(tmp_path)
    (tmp_path / "settlements.csv").write_text(
        "round,municipality_code,number,settlement,note\n"
        "r1,80357,1,Голубинци,the decision's address names the school's old building\n"
        "r1,80357,2,Овча,not in this municipality\n"
        "r1,80357,3,,a row without a settlement is skipped\n", encoding="utf-8")
    logged = []
    rules = S.load_rules(tmp_path / "settlements.csv", logged.append)
    stations = [st("1", "ОШ БРАНКО РАДИЧЕВИЋ"), st("2", "МЗ СТАРИ БАНОВЦИ")]
    got = S.join(stations, c, {"80357/1": "ОШ, Нови Бановци"}, "r1", rules, logged.append)
    assert got["80357/1"] == {"u": "Стара Пазова", "s": "Голубинци", "m": "manual"}
    assert got["80357/2"]["m"] == "station"  # the correction names another municipality's settlement
    assert len(logged) == 2


def test_a_municipality_rule_for_the_stations_nothing_places(tmp_path):
    """A row with number "*": the stations of the municipality no other rule places are in that settlement (the
    maintainer checked the commission writes bare building names for the town's stations only)."""
    c = census(tmp_path)
    (tmp_path / "settlements.csv").write_text(
        "round,municipality_code,number,settlement,note\n"
        "r1,80357,*,Стара Пазова,the commission writes only the building for the town's stations\n", encoding="utf-8")
    rules = S.load_rules(tmp_path / "settlements.csv")
    stations = [st("1", "ДОМ КУЛТУРЕ"), st("2", "МЗ СТАРИ БАНОВЦИ")]
    got = S.join(stations, c, {}, "r1", rules)
    assert got["80357/1"] == {"u": "Стара Пазова", "s": "Стара Пазова", "m": "rest"}
    assert got["80357/2"]["m"] == "station"  # a station a rule places keeps its own settlement


def test_the_same_place_in_another_election(tmp_path):
    c = census(tmp_path)
    old = [st("5", "МЗ СТАРИ БАНОВЦИ"), st("6", "ОШ СВЕТИ САВА")]
    new = [st("5", "МЗ СТАРИ БАНОВЦИ"), st("6", "ОШ СВЕТИ САВА")]
    joined = {"a": S.join(old, c, {"80357/6": "ОШ Свети Сава, Голубинци"}, "a"),
              "b": S.join(new, c, {"80357/6": "ОШ Свети Сава, Светосавска 16"}, "b")}
    assert joined["b"]["80357/6"]["m"] == "seat"
    places = follow([("a", old, {}), ("b", new, {})])
    assert S.inherit(joined, places) == 1
    assert joined["b"]["80357/6"] == {"u": "Стара Пазова", "s": "Голубинци", "m": "place"}  # rather than the seat
    assert joined["a"]["80357/5"]["m"] == "station"  # found by itself: kept


def test_the_store_is_one_station_per_line(tmp_path):
    joined = {"80357/1": {"u": "Стара Пазова", "s": "Нови Бановци", "m": "address"},
              "80357/2": {"u": "Стара Пазова", "s": "Голубинци", "m": "building"}}
    assert S.save_store(tmp_path, joined)
    text = (tmp_path / S.STORE).read_text(encoding="utf-8")
    assert text.count("\n") == len(joined) + 2
    assert json.loads(text) == {"census": "2022", "stations": joined}
    assert not S.save_store(tmp_path, joined)  # unchanged: not written


def test_the_2026_stations_have_their_settlements(archive, round2026):
    census = S.Census(S.load_units(archive.root / S.TABLE))
    assert len(census.units) == 168 and sum(len(u.settlements) for u in census.units) == 4721
    store = S.load_store(archive.dir(round2026.id))["stations"]
    by_key = {u.key: set(u.settlements) for u in census.units}
    assert all(e["m"] in S.HOW and e["s"] in by_key[e["u"]] for e in store.values())
    rnd = round2026
    units = census.for_round(rnd.stations)
    home = [s for s in rnd.stations if s.kind == "domestic" and units.get(s.municipality_code)]
    assert sum(s.key in store for s in home) / len(home) > 0.85
    vracar = [s for s in rnd.stations if s.municipality_code == "70114"]
    assert vracar and all(store[s.key]["s"] == "Београд (Врачар)" for s in vracar)


def figure_tables(data_dir):
    """The two tables the figures come from, in the Office's layout: B "г" for urban, J and K the 2011 and 2022
    population; and by age, three rows per place (both sexes first), 65-69 to 85+ in R to V."""
    base = data_dir / S.TABLES
    base.mkdir(parents=True)
    rows = [("Сремска област", 2, "", None, None), ("Стара Пазова", 2, "", 66000, 63000),
            ("Стара Пазова", 4, "г", 18000, 19000), ("Голубинци", 4, "", 5000, 4000), ("Нови Бановци", 4, "", "-", 300),
            ("Пчињска област", 2, "", None, None), ("Бујановац", 2, "", None, None), ("Биљача", 4, "", "...", 1976)]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Упоредни преглед броја становника"])
    for i, (name, indent, urban, p11, p22) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=name).alignment = Alignment(indent=indent)
        ws.cell(row=i, column=2, value=urban)
        ws.cell(row=i, column=10, value=p11)
        ws.cell(row=i, column=11, value=p22)
    wb.save(base / S.POPULATION.name)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Становништво према старости и полу"])
    r = 2
    for name, indent, _, _, p22 in rows:
        for sex in ("С", "М", "Ж"):
            if sex == "С":
                ws.cell(row=r, column=1, value=name).alignment = Alignment(indent=indent)
            ws.cell(row=r, column=3, value=sex)
            for col in range(18, 23):  # 65-69 … 85 and more
                ws.cell(row=r, column=col, value="-" if name == "Нови Бановци" else 100)
            r += 1
    wb.save(base / S.AGES.name)


def test_the_figures_of_each_settlement(tmp_path):
    figure_tables(tmp_path)
    fig = S.load_figures(tmp_path)
    assert set(fig) == {("Стара Пазова", "Стара Пазова"), ("Стара Пазова", "Голубинци"),
                        ("Стара Пазова", "Нови Бановци"), ("Бујановац", "Биљача")}
    town = fig[("Стара Пазова", "Стара Пазова")]
    assert town.urban and town.pop2022 == 19000 and town.old == 500
    assert abs(town.change - (19000 / 18000 - 1)) < 1e-12 and abs(town.share_old - 500 / 19000) < 1e-12
    assert not fig[("Стара Пазова", "Голубинци")].urban and abs(fig[("Стара Пазова", "Голубинци")].change + 0.2) < 1e-12
    # "-" is none, "..." unknown: no change from no one, nor from a figure the 2011 census doesn't give
    assert fig[("Стара Пазова", "Нови Бановци")].pop2011 == 0 and fig[("Стара Пазова", "Нови Бановци")].change is None
    assert fig[("Стара Пазова", "Нови Бановци")].old == 0
    assert fig[("Бујановац", "Биљача")].pop2011 is None and fig[("Бујановац", "Биљача")].change is None
    assert S.load_figures(tmp_path / "nothing") == {}


def test_the_archived_census_names_every_joined_settlement(archive):
    fig = S.load_figures(archive.root)
    assert len(fig) == 4721 and sum(f.urban for f in fig.values()) == 179
    units = S.load_units(archive.root / S.TABLE)
    assert set(fig) == {(u.key, s) for u in units for s in u.settlements}  # the tables agree on the hierarchy
    for rid in archive.round_ids():
        joined = S.load_store(archive.dir(rid)).get("stations", {})
        assert {(e["u"], e["s"]) for e in joined.values()} <= set(fig), rid
    # Preševo and Bujanovac: the 2011 census counted them only as municipalities
    assert all(f.pop2011 is None for (u, _), f in fig.items() if u == "Бујановац")


def test_a_decision_on_polling_stations_names_each_settlement(tmp_path):
    """A commission's act on polling stations (made-up): one row per station with number, name, address and area;
    the settlement in the row is the station's, when the row looks like the station (a shared word in the name)."""
    from izbori import stationlist
    c = census(tmp_path)
    units = c.for_round([st("1")])["80357"]
    act = ("На основу члана 56. Закона ... доноси РЕШЕЊЕ о одређивању бирачких места\n"
           "Р.бр. | Назив | Адреса | Подручје\n"
           "1 | ОШ „Бошко Палковљевић Пинки“ | Стара Пазова, Ћирила и Методија 1 | улице: Ћирила и Методија, Карађорђева 1-99\n"
           "2 | Дом културе | Голубинци, Путиначка 2 | насеље Голубинци\n"
           "3 | Месна заједница | Нови Бановци, Светосавска 1 | Нови Бановци (цело насеље)\n"
           "4 | ОШ „Симеон Араницки“ | Стара Пазова, Светосавска 5 | улице: Светосавска 1-50\n")
    stations = [st("1", "ОШ БОШКО ПАЛКОВЉЕВИЋ ПИНКИ"), st("2", "ДОМ КУЛТУРЕ"), st("3", "ОШ ВУК КАРАЏИЋ"),
                st("4", "ОСНОВНА ШКОЛА")]  # 3: another building than the act's row (renumbered); 4: a bare kind
    got = stationlist.read_act(act, stations, units)
    assert got == {"80357/1": {"s": "Стара Пазова", "ok": True}, "80357/2": {"s": "Голубинци", "ok": True},
                   "80357/3": {"s": "Нови Бановци", "ok": False}, "80357/4": {"s": "Стара Пазова", "ok": True}}
    rows = stationlist.rows("1. Школа, Голубинци 2\n2. Дом, кућни број 12\n3. Трећи", 3)
    assert rows == {1: " Школа, Голубинци 2", 2: " Дом, кућни број 12", 3: " Трећи"}  # 12 and 2 inside rows pass
    # the join takes the act's settlement before the address, and passes it on like any certain rule
    got = S.join(stations[:2], c, {"80357/2": "Дом културе, Путиначка 2"}, "r1", listed={"80357/2": "Голубинци"})
    assert got["80357/2"] == {"u": "Стара Пазова", "s": "Голубинци", "m": "list"} and "list" in S.DIRECT
    # an address that names a settlement itself wins over the act's row (rows can come out shifted)
    got = S.join(stations[:2], c, {"80357/2": "Дом културе, Голубинци, Путиначка 2"}, "r1", listed={"80357/2": "Нови Бановци"})
    assert got["80357/2"]["s"] == "Голубинци" and got["80357/2"]["m"] == "address"


def test_an_act_whose_rows_sit_above_their_numbers(tmp_path):
    """Cells of several lines put a row's address above its number in the extracted text (Barajevo 2026): the
    reading agreeing with the board decisions' explicit addresses is kept, and an act agreeing with too few of
    them is set aside."""
    from izbori import stationlist
    c = census(tmp_path)
    units = c.for_round([st("1")])["80357"]
    act = ("РЕШЕЊЕ\nДом културе Голубинци\n1\nМесна заједница Нови Бановци\n2\nДом Стари Бановци\n3\nкрај\n")
    stations = [st("1", "ДОМ КУЛТУРЕ"), st("2", "МЕСНА ЗАЈЕДНИЦА"), st("3", "ДОМ")]
    checks = {"80357/1": "Голубинци", "80357/2": "Нови Бановци", "80357/3": "Стари Бановци"}
    rep = {}
    got = stationlist.read_act(act, stations, units, checks, rep)
    assert rep["kept"] == "before" and {k: v["s"] for k, v in got.items()} == checks
    act5 = act.replace("крај", "Школа Голубинци\n4\nШкола Нови Бановци\n5\nкрај")
    wrong = {f"80357/{n}": "Стара Пазова" for n in range(1, 6)}
    rep = {}
    more = stations + [st("4", "ШКОЛА"), st("5", "ШКОЛА")]
    assert stationlist.read_act(act5, more, units, wrong, rep) == {} and rep["kept"] is None


def test_an_amendment_adds_to_the_decision_it_amends():
    from izbori import stationlist
    store = {"docs": {"a": {"st": {"1/1": {"s": "A", "ok": True}, "1/2": {"s": "B", "ok": True}}},
                      "b": {"st": {"1/2": {"s": "C", "ok": True}, "1/3": {"s": "D", "ok": False}}}},
             "stations": {"1/9": {"s": "old", "ok": True}, "2/1": {"s": "X", "ok": True}}}
    stationlist.merge(store, [{"url": "a"}, {"url": "b"}], "1")
    assert store["stations"] == {"1/1": {"s": "A", "ok": True}, "1/2": {"s": "C", "ok": True},
                                 "1/3": {"s": "D", "ok": False}, "2/1": {"s": "X", "ok": True}}
    # an act read before its stations were kept: the municipality's stations so far stay
    store = {"docs": {"a": {"rows": 3}, "b": {"st": {"1/2": {"s": "C", "ok": True}}}},
             "stations": {"1/1": {"s": "A", "ok": True}}}
    stationlist.merge(store, [{"url": "a"}, {"url": "b"}], "1")
    assert store["stations"] == {"1/1": {"s": "A", "ok": True}, "1/2": {"s": "C", "ok": True}}
