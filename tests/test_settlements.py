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
