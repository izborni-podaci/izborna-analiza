"""The same polling place across elections: by address, then name, then number."""

from izbori.model import Station
from izbori.places import follow


def st(number: str, name: str = "", code: str = "70092") -> Station:
    return Station(key=f"{code}/{number}", uid=number, number=number, name=name, municipality="Барајево",
                   municipality_code=code, district="", district_code="RS11", registered=100, voted=50, ballots=50,
                   valid=50, invalid=0, entered="", votes=[50])


def chains(places) -> dict[str, list[tuple[str, str, str]]]:
    """place id → [(round, number, how joined)], newest election first"""
    return {p.id: [(r, p.stations[r].number, p.how[r]) for r in p.rounds] for p in places.places}


def test_name_before_number():
    # the gymnasium was 10 and is now 14; 10 is now another school
    old = [st("10", "ЗЕМУНСКА ГИМНАЗИЈА"), st("11", "ОШ ЛАЗА КОСТИЋ")]
    new = [st("10", "ПРАВНО ПОСЛОВНА ШКОЛА"), st("14", "Земунска гимназија"), st("11", "ОШ „ЛАЗА КОСТИЋ“")]
    got = chains(follow([("a", old, {}), ("b", new, {})]))
    assert got["70092-14"] == [("b", "14", ""), ("a", "10", "name")]
    assert got["70092-11"] == [("b", "11", ""), ("a", "11", "name")]
    assert got["70092-10"] == [("b", "10", "")]


def test_number_never_joins_clearly_different_names():
    old = [st("2", "СКУПШТИНА ОПШТИНЕ - ВЕЛИКА САЛА")]
    new = [st("2", "ОШ КНЕЗ СИМА МАРКОВИЋ")]
    got = chains(follow([("a", old, {}), ("b", new, {})]))
    assert got == {"70092-2": [("b", "2", "")], "70092-2-a": [("a", "2", "")]}


def test_number_joins_when_names_share_a_word_or_are_missing():
    old = [st("1", "МК АРНАЈЕВО"), st("7", "МЕСНА ЗАЈЕДНИЦА Г.БРДО - ЛИПОВИЦА"), st("8", "")]
    new = [st("1", "ОШ АРНАЈЕВО"), st("7", "МЕСНА ЗАЈЕДНИЦА ГЛУМЧЕВО БРДО - ЛИПОВИЦА"), st("8", "ДОМ КУЛТУРЕ")]
    got = chains(follow([("a", old, {}), ("b", new, {})]))
    assert got["70092-1"][1] == ("a", "1", "name")  # МК and ОШ are too short to tell; Арнајево is the name
    assert got["70092-7"][1] == ("a", "7", "number")
    assert got["70092-8"][1] == ("a", "8", "number")  # "дом културе" alone says nothing


def test_older_election_without_names_follows_the_nearest_number():
    oldest = [st("10"), st("14")]  # RIK's 2022 table has no names
    old = [st("10", "ЗЕМУНСКА ГИМНАЗИЈА"), st("14", "ОШ СВЕТИ САВА")]
    new = [st("14", "ЗЕМУНСКА ГИМНАЗИЈА"), st("20", "ОШ СВЕТИ САВА")]
    got = chains(follow([("z", oldest, {}), ("a", old, {}), ("b", new, {})]))
    assert got["70092-14"] == [("b", "14", ""), ("a", "10", "name"), ("z", "10", "number")]
    assert got["70092-20"] == [("b", "20", ""), ("a", "14", "name"), ("z", "14", "number")]


def test_shared_venue_pairs_equal_numbers_then_in_order():
    old = [st("5", "ОШ ВЕЉКО ПЕТРОВИЋ"), st("6", "ОШ ВЕЉКО ПЕТРОВИЋ"), st("9", "ОШ ВЕЉКО ПЕТРОВИЋ")]
    new = [st("7", "Основна школа Вељко Петровић"), st("8", "ОШ ВЕЉКО ПЕТРОВИЋ"), st("9", "ОШ ВЕЉКО ПЕТРОВИЋ")]
    got = chains(follow([("a", old, {}), ("b", new, {})]))
    assert got["70092-9"][1] == ("a", "9", "name")
    assert got["70092-7"][1] == ("a", "5", "name")
    assert got["70092-8"][1] == ("a", "6", "name")


def test_address_before_name_and_number():
    # one school's two buildings swapped numbers; the address tells them apart
    old = [st("5", "ОСНОВНА ШКОЛА"), st("6", "ОСНОВНА ШКОЛА")]
    new = [st("5", "ОСНОВНА ШКОЛА"), st("6", "ОСНОВНА ШКОЛА")]
    old_addr = {"70092/5": "ОСНОВНА ШКОЛА, ДОЊА ЛОКОШНИЦА", "70092/6": "ОСНОВНА ШКОЛА, БРЕСТОВАЦ"}
    new_addr = {"70092/5": "Основна школа, Брестовац", "70092/6": "ОСНОВНА ШКОЛА, ДОЊА ЛОКОШНИЦА"}
    places = follow([("a", old, old_addr), ("b", new, new_addr)])
    got = chains(places)
    assert got["70092-5"][1] == ("a", "6", "address")
    assert got["70092-6"][1] == ("a", "5", "address")
    assert places.of("a", "70092/6").address == "Основна школа, Брестовац"  # the newest address


def test_clearly_different_addresses_keep_places_apart():
    old = [st("3", "ОСНОВНА ШКОЛА")]
    new = [st("3", "ОСНОВНА ШКОЛА")]
    places = follow([("a", old, {"70092/3": "ОШ, СИНОШЕВИЋ"}), ("b", new, {"70092/3": "ОШ, НАКУЧАНИ"})])
    assert len(places.places) == 2


def test_municipalities_never_mix():
    places = follow([("a", [st("1", "ДОМ", code="1")], {}), ("b", [st("1", "ДОМ", code="2")], {})])
    assert sorted(p.id for p in places.places) == ["1-1", "2-1"]


def test_real_archive(archive):
    from izbori import boards
    rounds = [(r, archive.load(r).stations, boards.addresses(boards.load_store(archive.dir(r))))
              for r in archive.round_ids()]
    places = follow(rounds)
    assert sum(len(p.rounds) for p in places.places) == sum(len(s) for _, s, _ in rounds)  # every station, once
    assert len({p.id for p in places.places}) == len(places.places)
    for rid, stations, _ in rounds:
        assert all(places.of(rid, s.key).stations[rid] is s for s in stations)
    zemun = next(p for p in places.places if p.id == "70157-14")
    assert [zemun.stations[r].number for r in zemun.rounds] == ["14", "14", "10", "10"]
