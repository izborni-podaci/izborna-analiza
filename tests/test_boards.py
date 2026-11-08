"""Controllers from board decisions. The fixture is a made-up decision with invented names."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from izbori.boards import (PARSER, BoardDoc, classify, coverage, match_list, municipality_key, named_most, parse_decision,
                           parse_index_records, pdf_text, read_columns, slot_list, standing_under_extended)

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def contestants(archive):
    return archive.meta("680072")["contestants"]


def test_parse_decision_text():
    d = parse_decision((FIX / "board_decision.txt").read_text(encoding="utf-8"))
    assert d.station == "12"
    assert d.address == 'ОШ "ВУК КАРАЏИЋ", ПРИМЕР, ГЛАВНА 1'
    assert [(s.member, s.deputy) for s in d.slots] == [(True, True), (False, False), (True, False), (True, False)]


LISTS = ("АЛЕКСАНДАР ВУЧИЋ – УЈЕДИЊЕНА СРБИЈА", "ИВИЦА ДАЧИЋ – ФАКТОР СТАБИЛНОСТИ!",
         "„Студентска листа - Студенти побеђују“")
HEAD = ("На основу члана 32. тачка 2) Закона, Општинска изборна комисија, на предлог секретара, донела је\nРЕШЕЊЕ\n"
        "ЗА БИРАЧКО МЕСТО БРОЈ 21 У ОПШТИНИ ПРИМЕР\nОШ „ПРИМЕР“, ГЛАВНА 1\n1. У бирачки одбор у проширеном саставу "
        "за бирачко место број 21 у општини Пример именују се:\n")
TAIL = "2. Ово решење објављује се на веб-презентацији Републичке изборне комисије.\n"


def lists_of(d, contestants):
    """Per ballot number, (member, deputy), the slots of one list added up as the coverage does."""
    out = {}
    for s in d.slots:
        n = match_list(s.list_text, contestants)
        m, dep = out.get(n, (False, False))
        out[n] = (m or s.member, dep or s.deputy)
    return out


def test_decisions_in_other_layouts(contestants):
    """Layouts of whole municipalities that weren't read on 5 Nov 2026 (as their masked layouts showed): members
    numbered "1)"; unnumbered, each role with its own list; and each list first with its people under it."""
    a, b, c = LISTS
    numbered = HEAD + (f"1) ЧЛАН: Петар Петровић и\n\n- ЗАМЕНИК ЧЛАНА: Марко Марковић, на предлог подносиоца изборне "
                       f"листе: {a}\n2) ЧЛАН: и\n- ЗАМЕНИК ЧЛАНА: , на предлог подносиоца изборне листе: {b}\n"
                       f"3) ЧЛАН: Ана Анић, на предлог подносиоца изборне листе: {c}\n") + TAIL
    assert lists_of(parse_decision(numbered), contestants) == {1: (True, True), 2: (False, False), 3: (True, False)}
    each_role = HEAD + (f"- члан: Петар Петровић и на предлог подносиоца Изборне листе {a};\n\n- заменик члана: Марко "
                        f"Марковић, на предлог подносиоца Изборне листе {a};\n\n- члан: Ана Анић на предлог "
                        f"подносиоца Изборне листе {c};\n") + TAIL
    assert lists_of(parse_decision(each_role), contestants) == {1: (True, True), 3: (True, False)}
    pairs = HEAD + (f"- Члан: Петар Петровић и\n\n– Заменик члана: Марко Марковић , на предлог подносиоца\nИзборне "
                    f"листе: {a};\n\n- Члан: и\n\n– Заменик члана: Јован Јовић, на предлог подносиоца\nИзборне листе: "
                    f"{b};\n") + TAIL
    assert lists_of(parse_decision(pairs), contestants) == {1: (True, True), 2: (False, True)}
    list_first = HEAD + (f"|. На предлог подносиоца изборне листе {a}:\nчлан: Петар Петровић\n\n- заменик члана Марко "
                         f"Марковић\n\n2. На предлог подносиоца изборне листе {c}:\nчлан: Ана Анић\n\n- заменик члана\n"
                         ) + TAIL
    assert lists_of(parse_decision(list_first), contestants) == {1: (True, True), 3: (True, False)}
    # the address and the station are read as before
    d = parse_decision(list_first)
    assert (d.station, d.address) == ("21", "ОШ \"ПРИМЕР\", ГЛАВНА 1")


def test_a_misread_na_before_predlog_keeps_the_slot(contestants):
    """Mali Iđoš, 8 Nov 2026: OCR read "на предлог" as "ха предлог" or "иа предлог" in three of six slots, and those
    three slots (the Student list's among them) were dropped, so the station showed no controller of theirs."""
    a, b, c = LISTS
    text = HEAD + (f"1. члан: Петар Петровић и\n\n- заменик члана: Марко Марковић на предлог подносиоца Изборне листе "
                   f"{a};\n\n2. члан: Јован Јовић и\n\n- заменик члана: Ана Анић ха предлог подносиоца Изборне листе "
                   f"{b};\n\n3. члан: Лука Лукић и\n\n- заменик члана: Мина Минић иа предлог подносиоца Изборне листе "
                   f"{c};\n") + TAIL
    assert lists_of(parse_decision(text), contestants) == {1: (True, True), 2: (True, True), 3: (True, True)}


def test_a_garbled_clan_still_starts_a_slot(contestants):
    """Mali Iđoš station 16, 8 Nov 2026: OCR read the fourth slot's "члан" as another word, so the fourth slot ran
    into the third, which then named two lists and kept the wrong one."""
    a, b, c = LISTS
    text = HEAD + (f"1. члан: Петар Петровић и\n\n- заменик члана: Марко Марковић на предлог подносиоца Изборне листе "
                   f"{a};\n\n3. члан: Лука Лукић и\n\n- заменик члана: Мина Минић на предлог подносиоца Изборне листе "
                   f"{c};\n\n4. чпан: Јован Јовић и\n\n- заменик чпана: Ана Анић на предлог подносиоца Изборне листе "
                   f"{b};\n") + TAIL
    assert lists_of(parse_decision(text), contestants) == {1: (True, True), 3: (True, True), 2: (True, True)}


def test_lists_match_despite_ocr_noise(contestants):
    # strings as OCR returned them from real decisions, including garbled Latin parts
    cases = {
        "АЛЕКСАНДАР ВУЧИЋ - УЈЕДИЊЕНИ СРБИЈА": 1,
        "ИВИЦА ДАЧИЋ - ФАКТОР СТАБИЛНОСТИ!": 2,
        '"Студентска листа - Студенти побеђују"': 3,
        "РАСИМ ЉАЈИЋ - Људски (СДП - ЦДП)": 4,
        "Мајдазад! Magyar Szovetseg - Dr. Разлог Ват! - Савез војвођанских Мађара - др Балинт Пастор": 5,
        "Џзате Zukorlić (SPP) Pokret ха ujedinjenje / Усаме Зукорлић (СПП) Покрет за уједињење": 6,
        "РУСКА СТРАНКА - СРБИЈА У БРИКСУ - СЛОБОДАН НИКОЛИЋ": 7,
        "АУТЕНТИЧНА ДЕСНИЦА - др МИЛОШ ЈОВАНОВИЋ (Нови ДСС - МОНАРХИСТИ)": 8,
        "ЕВРОПСКА СРБИЈА - МАРИНИКА ТЕПИЋ - ЗДРАВКО ПОНОШ": 9,
        "СДА Санџака - ЧУВАРИ САНЏАКА SDA Sandžaka - ČUVARI SANDŽAKA": 10,
        "Богољуб Карић - Покрет СНАГА СРБИЈЕ - БК": 11,
        "ЛИБЕРАЛНА ЗЕЛЕНА СТРАНКА - ЗА СЛОБОДНУ И ЧИСТУ СРБИЈУ": 12,
        "Бирам ПРАВДУ - Бирам БУДУЋНОСТ - Коалиција СНАГА - проф. др Ферид Булић": 13,
        "СТРАНКА РУСКО - СРПСКОГ ЈЕДИНСТВА - РУСИ И СРБИ БРАЋА ЗАУВЕК": 14,
        "ЋАЛЕ ОВО ЈЕ ЗА ТЕБЕ - ПЕТАР ЂУРИЋ - ПРЕМИЈЕР СРБИЈЕ": 15,
        "ВЛАДИМИР ГАЈИЋ АЛТЕРНАТИВА ЗА СРБИЈУ - НАРОДНА СТРАНКА, БУНТ - ПРАВА СРБИЈА": 16,
        '"АЛБАНСКА КОАЛИЦИЈА" - "KOALICIONI SHQIPTAR"': 17,
        "МАЈКА СРБИЈА - ГРУДА": 18,
    }
    for text, number in cases.items():
        assert match_list(text, contestants) == number, text
    assert match_list("НЕКА СЕДМА ГРУПА ГРАЂАНА", contestants) is None


@pytest.mark.skipif(not shutil.which("tesseract") or "srp" not in subprocess.run(
    ["tesseract", "--list-langs"], capture_output=True, text=True, env=os.environ).stdout, reason="no Serbian OCR")
def test_ocr_of_a_scan():
    d = parse_decision(pdf_text((FIX / "board_decision.pdf").read_bytes()))
    assert d.station == "12"
    assert [(s.member, s.deputy) for s in d.slots] == [(True, True), (False, False), (True, False), (True, False)]


def test_table_rows_each_role_with_its_own_proposal():
    """A scan of a table read line by line (Ub, 2026; made-up names): each row is a member or a deputy with their own
    proposal, the slots numbered by ballot, and a row's proposal often on the line above its slot's number. Each
    slot's list is the one it names most; a slot whose number OCR lost still gives its deputy."""
    import json
    contestants = json.loads((Path(__file__).parents[1] / "data/rounds/680072/meta.json").read_text(
        encoding="utf-8"))["contestants"]
    d = parse_decision((FIX / "board_table_rows.txt").read_text(encoding="utf-8"))
    assert d.station == "2"
    assert [[slot_list(s, contestants), s.member, s.deputy] for s in d.slots] == [
        [1, True, True], [2, False, True], [3, True, True], [7, True, True], [15, True, True]]
    # a member's surname that is also a list's leader's (7: Nikolić) doesn't move the slot to that list
    assert named_most("члан Петар Николић из Села АЛЕКСАНДАР ВУЧИЋ - УЈЕДИЊЕНА СРБИЈА заменик члана на предлог "
                      "АЛЕКСАНДАР ВУЧИЋ - УЈЕДИЊЕНА СРБИЈА", contestants) == 1


def test_a_table_read_by_columns_is_told():
    by_columns = "1) члан x\n9)\n\n12)\n\nчлан\n\nзаменик члана\n\nчлан\n\nзаменик члана\n"
    assert read_columns(by_columns)
    assert not read_columns("1. члан: Петар Петровић, на предлог подносиоца изборне листе X;\n2. члан: ...")


def test_classify():
    assert classify("РЕШЕЊЕ О ИМЕНОВАЊУ ЧЛАНОВА ... У ПРОШИРЕНОМ САСТАВУ БМ 77", "") == ("extended", False)
    assert classify("БМ 11", "Решење о именовању члана и заменика члана бирачког одбора у проширеном саставу") \
        == ("extended", False)
    assert classify("РЕШЕЊЕ", "Решење о именовању члана ... у проширеном саставу – поновно гласање") == ("extended", True)
    assert classify("РЕШЕЊЕ О ИМЕНОВАЊУ ... У СТАЛНОМ САСТАВУ", "Решење ... у проширеном саставу")[0] == "extended"
    assert classify("РЕШЕЊЕ О ИМЕНОВАЊУ ПРЕДСЕДНИКА ... У СТАЛНОМ САСТАВУ", "")[0] == "standing"


def test_standing_composition_under_the_extended_label():
    """Ub, 2026: the commission uploaded each station's standing composition under the extended's label, so a station
    had two "extended" decisions and no standing one; the title of one names the president. Ada's titles name the
    standing composition on both of a station's decisions, under two labels: there the labels stand."""
    def doc(i, title, label, station="2"):
        kind, repeat = classify(title, label)
        return BoardDoc(id=i, municipality="Уб", station=station, title=title, decision=label, published="", url="",
                        kind=kind, repeat=repeat)
    extended = "Решење о именовању члана и заменика члана бирачког одбора у проширеном саставу"
    standing = "Решење о именовању председника, чланова бирачког одбора и њихових заменика у сталном саставу"
    ub = [doc("1", "Решење о именовању чланова и њихових заменика у проширеном саставу за бирачко место број 2",
              extended),
          doc("2", "Решење о именовању преседника и члана бирачког одбора и њихових заменика за бирачко место број 2",
              extended)]
    assert standing_under_extended([(d, "71218/2") for d in ub], {}) == {"2"}
    ada = [doc("3", "Решење о именовању председника и чланова бирачког одбора", standing),
           doc("4", "Решење о именовању председника и чланова бирачког одбора", extended)]
    assert [d.kind for d in ada] == ["standing", "extended"]
    assert standing_under_extended([(d, "80012/1") for d in ada], {}) == set()
    # the station's standing decision may be in the store from an earlier pass
    assert standing_under_extended([(ub[1], "71218/2")], {"9": {"s": "71218/2", "k": "standing"}}) == set()
    assert classify("", "Решење о одбијању предлога ... у проширеном саставу")[0] == "extended_rejected"
    assert classify("", "Решење о измени решења ... у проширеном саставу")[0] == "extended_change"
    assert classify("РЕШЕЊЕ О ИЗМЕНИ РЕШЕЊА БО - БМ 25", "Решење о измени решења о именовању члана / заменика члана "
                    "бирачког одбора у сталном саставу – поновно гласање") == ("standing_change", True)


def test_index_records():
    rec = {"datetime": "1793400468", "document_bearer": "Општинска изборна комисија општине Куршумлија",
           "document_name": "РЕШЕЊЕ О ИМЕНОВАЊУ ЧЛАНА И ЗАМЕНИКА ЧЛАНА БИРАЧКОГ ОДБОРА У ПРОШИРЕНОМ САСТАВУ",
           "election_board_decision": "Решење о именовању ... у проширеном саставу – поновно гласање",
           "election_station_title": "30 - ОСНОВНА ШКОЛА",
           "extfiles_link": ['<div><a href="/extfile/sr/files/additionalDocuments/819/743/x.pdf"></a></div>'],
           "municipality_display_name": "Куршумлија"}
    [d] = parse_index_records([rec])
    assert (d.id, d.station, d.kind, d.repeat) == ("819743", "30", "extended", True)


def test_municipality_names_match_the_results_file(round2026):
    keys = {municipality_key(s.municipality): s.municipality_code for s in round2026.stations}
    assert keys[municipality_key("Палилула (Београд)")] == next(
        s.municipality_code for s in round2026.stations if s.municipality == "Градска општина Палилула (Београд)")
    assert municipality_key("Земун ") in keys
    assert municipality_key("Нови Сад") in keys


def test_a_city_commission_s_decisions_find_their_station():
    """In 2026 Požarevac's commission listed Kostolac's decisions under Požarevac with Kostolac's own numbers, and
    Niš's were listed under a name the results don't use: the station's name in the register says which station
    it is. Nothing else moves: a generic name, or one that fits two stations, stays where the register puts it."""
    from types import SimpleNamespace as NS

    from izbori.boards import Placer

    def st(code, mun, number, name, district="11"):
        return NS(key=f"{code}/{number}", municipality_code=code, municipality=mun, number=number, name=name,
                  district_code=district)
    stations = [st("70947", "Град Пожаревац", "1", "ОСНОВНА ШКОЛА"), st("70947", "Град Пожаревац", "2", "ДОМ"),
                st("71340", "Градска општина Костолац", "1", "ДОМ КУЛТУРЕ"),
                st("70100", "Голубац", "1", "ДОМ КУЛТУРЕ"),  # same district, not a city municipality
                st("71331", "Градска општина Медијана", "7", 'ОШ "ЦАР КОНСТАНТИН"', "12"),
                st("71307", "Градска општина Пантелеј", "7", 'ОШ "ЧЕГАР"', "12"),
                st("33000", "Иностранство", "3", "АМБАСАДА РС БЕЧ – КОНЗУЛАРНО ОДЕЉЕЊЕ", "33000"),
                st("55001", "Заводи за извршење кривичних санкција", "3", "КПЗ ПРИМЕР", "55001")]
    codes = {municipality_key(s.municipality): s.municipality_code for s in stations}
    names = {"71331": {municipality_key("Ниш-Медијана")}, "71307": {municipality_key("Ниш-Пантелеј")}}  # 2022
    p = Placer(codes, stations, names)
    assert p.place("Пожаревац", "1", "ОСНОВНА ШКОЛА") == ("70947/1", "direct")
    assert p.place("Пожаревац", "1", "ДОМ КУЛТУРЕ") == ("71340/1", "moved")
    assert p.place("Пожаревац", "2", "ДОМ КУЛТУРЕ") == ("70947/2", "as listed")  # Kostolac has no station 2
    assert p.place("Пожаревац", "1", "") == ("70947/1", "direct")
    assert p.place("Ниш", "7", "ОШ „Чегар“") == ("71307/7", "named")
    assert p.place("Ниш", "7", "ДРУГА ШКОЛА") == (None, "unknown municipality")
    assert p.place("Пожаревац", "", "ДОМ") == (None, "no number")
    assert p.place("Пожаревац", "9", "ДОМ") == (None, "no such station")
    # a city's commission under the city's name, its city municipalities known only by their district
    vozdovac = [st("70106", "Градска општина Вождовац", "4", "ОШ „Бранко Ћопић“", "1")]
    vozdovac[0].district = "Београдски регион"
    assert Placer({}, vozdovac).place("Београд", "4", 'ОШ "БРАНКО ЋОПИЋ"') == ("70106/4", "named")
    # RIK lists the boards it appoints itself, abroad and in prisons, under its own name
    assert p.place("РИК", "3", "АМБАСАДА РС БЕЧ - КОНЗУЛАРНО ОДЕЉЕЊЕ") == ("33000/3", "named")
    assert p.place("РИК", "3", "КПЗ ПРИМЕР") == ("55001/3", "named")
    assert Placer(codes).place("Пожаревац", "9") == ("70947/9", "direct")  # without the results' stations, as before


def test_a_better_placement_reaches_decisions_already_read():
    from izbori.boards import apply_index
    store = {"docs": {"1": {"s": "70947/1", "k": "extended", "slots": [[1, True, False]], "u": "/a"},
                      "2": {"s": None, "k": "extended", "slots": [[2, True, True]], "u": "/b"}}}
    apply_index(store, {"whole": True, "index": [
        {"id": "1", "s": "71340/1", "k": "extended", "r": False, "t": "", "u": "/a"},
        {"id": "2", "s": "71307/7", "k": "extended", "r": False, "t": "", "u": "/b"}]})
    assert store["docs"]["1"]["s"] == "71340/1" and store["docs"]["1"]["slots"] == [[1, True, False]]
    assert store["docs"]["2"]["s"] == "71307/7"
    # a decision read as the extended composition that the current rules call the standing one: no controllers
    apply_index(store, {"whole": True, "index": [
        {"id": "1", "s": "71340/1", "k": "standing", "r": False, "t": "", "u": "/a"}]})
    assert store["docs"]["1"]["k"] == "standing" and "71340/1" not in coverage(store)


def test_coverage_combines_and_prefers_repeat_votes():
    store = {"docs": {
        "a": {"s": "1/1", "k": "extended", "r": False, "t": "1", "slots": [[1, True, True], [3, False, False]],
              "addr": "X"},
        "b": {"s": "1/1", "k": "extended", "r": False, "t": "2", "slots": [[3, True, False]], "addr": ""},
        "c": {"s": "1/2", "k": "extended", "r": False, "t": "1", "slots": [[1, True, True]], "addr": ""},
        "d": {"s": "1/2", "k": "extended", "r": True, "t": "3", "slots": [[2, True, False]], "addr": "Y"},
        "e": {"s": "1/2", "k": "extended_rejected", "r": False, "t": "1"},
    }}
    cov = coverage(store)
    assert cov["1/1"]["lists"] == {"1": {"member": True, "deputy": True}, "3": {"member": True, "deputy": False}}
    assert cov["1/1"]["address"] == "X"
    assert cov["1/2"]["lists"] == {"2": {"member": True, "deputy": False}}


def test_unreadable_decision_is_unknown_not_empty():
    store = {"docs": {"a": {"s": "1/1", "k": "extended", "r": False, "t": "1", "slots": [], "unparsed": True}}}
    assert coverage(store)["1/1"]["lists"] is None


def test_shape_masks_names():
    from izbori.boards import shape
    text = (FIX / "board_decision.txt").read_text(encoding="utf-8")
    masked = shape(text)
    assert "Петар" not in masked and "Петровић" not in masked and "Марковић" not in masked
    assert "члан" in masked and "предлог" in masked


def index_page(records, pages=1):
    return {"records": records, "pagination": "".join(f'<a data-page="{p}">{p}</a>' for p in range(1, pages + 1))}


def index_record(n, station, decision, name="РЕШЕЊЕ"):
    return {"datetime": "1793400468", "document_name": name, "election_board_decision": decision,
            "election_station_title": f"{station} - ОШ", "municipality_display_name": "Куршумлија",
            "extfiles_link": [f'<div><a href="/extfile/sr/files/additionalDocuments/819/{n}/Решење БМ {station}.pdf">'
                              "</a></div>"]}


def test_links_are_kept_and_filled_in_for_decisions_read_before(tmp_path):
    """A store from before links were kept gets them from one pass through the whole register, and the kinds of
    the decisions not read with OCR follow the register; decisions read with OCR keep what was read."""
    import json

    from izbori.boards import load_store, run, station_docs
    records = [index_record(701, 30, "Решење о измени решења о именовању члана бирачког одбора у сталном саставу"),
               index_record(702, 30, "Решење о именовању члана и заменика члана бирачког одбора у проширеном саставу"),
               index_record(703, 31, "Решење о именовању члана бирачког одбора у сталном саставу")]
    (tmp_path / "boards.json").write_text(json.dumps({"complete": True, "docs": {
        "819701": {"s": "70017/30", "k": "standing", "r": False, "t": "1793400468"},
        "819702": {"s": "70017/30", "k": "extended", "r": False, "t": "1793400468", "slots": [[1, True, False]],
                   "addr": "ОШ"},
        "819600": {"s": "70017/31", "k": "standing", "r": False, "t": "1"},  # no longer in RIK's register
    }}, ensure_ascii=False), encoding="utf-8")

    class Client:
        base = "https://rik.test"
        calls = 0

        def get_json(self, path):
            Client.calls += 1
            return index_page(records)

    client = Client()
    stations = {municipality_key("Куршумлија"): "70017"}
    result = run(tmp_path, "680072", 2, [], stations, client, workers=1, log=lambda m: None)
    assert result["read"] == 0
    docs = load_store(tmp_path)["docs"]
    assert docs["819701"]["k"] == "standing_change" and docs["819701"]["u"].endswith("/819/701/Решење БМ 30.pdf")
    assert docs["819702"]["slots"] == [[1, True, False]]
    assert docs["819702"]["u"].endswith("/819/702/Решење БМ 30.pdf")
    assert docs["819703"] == {"s": "70017/31", "k": "standing", "r": False, "t": "1793400468",
                              "u": "/extfile/sr/files/additionalDocuments/819/703/Решење БМ 31.pdf"}
    assert docs["819600"]["u"] == ""
    linked = station_docs(load_store(tmp_path))
    assert [(d.kind, d.uploaded) for d in linked["70017/30"]] == [("board_standing_change", "2026-10-30T23:47"),
                                                                    ("board_extended", "2026-10-30T23:47")]
    assert linked["70017/30"][0].url == "https://www.rik.parlament.gov.rs/extfile/sr/files/additionalDocuments/819/701/" \
                                        "Решење БМ 30.pdf"
    assert [d.kind for d in linked["70017/31"]] == ["board_standing"]  # the decision without a link isn't listed
    # with every link kept, the next run only reads the register's newest page
    Client.calls = 0
    run(tmp_path, "680072", 2, [], stations, client, workers=1, log=lambda m: None)
    assert Client.calls == 1


def test_a_members_line_is_never_kept_as_the_address(tmp_path):
    """Where a decision has no address line, the first member's line (with a name) follows the station number: it
    is not an address, and one kept by an earlier version is dropped when the store is read or written."""
    import json

    from izbori.boards import addresses, load_store, save_store
    text = ("РЕШЕЊЕ\nУ бирачки одбор за бирачко место број 14\n1. члан: Петар Петровић из Вајске и\n"
            "заменик члана: Марко Марковић, на предлог подносиоца изборне листе ПРВА ЛИСТА\n")
    assert parse_decision(text).address == ""
    assert parse_decision("БИРАЧКО МЕСТО БРОЈ 12\nОШ \"ВУК КАРАЏИЋ\", ГЛАВНА 1\n").address == 'ОШ "ВУК КАРАЏИЋ", ГЛАВНА 1'
    (tmp_path / "boards.json").write_text(json.dumps({"docs": {
        "a": {"s": "1/1", "k": "extended", "addr": "1) ЧЛАН: ПЕТАР ПЕТРОВИЋ, на предлог подносиоца"},
        "b": {"s": "1/2", "k": "extended", "addr": "ОШ ПРИМЕР, ГЛАВНА 1"}}}, ensure_ascii=False), encoding="utf-8")
    store = load_store(tmp_path)
    assert addresses(store) == {"1/2": "ОШ ПРИМЕР, ГЛАВНА 1"}
    save_store(tmp_path, store)
    assert "ПЕТРОВИЋ" not in (tmp_path / "boards.json").read_text(encoding="utf-8")


def test_an_address_naming_another_building_is_not_used():
    from izbori.places import contradicts
    assert contradicts('ОШ "ЛАЗАР САВАТИЋ"', "ЗЕМУНСКА ГИМНАЗИЈА, ГРАДСКИ ПАРК БР. 2")
    assert contradicts('ОШ "СУТЈЕСКА"', "РАШКА")  # only the town
    assert not contradicts('ОШ "ЛАЗАР САВАТИЋ"', 'ОШ"ЛАЗАР САВАТИЋ", КЕЈ ОСЛОБОЂЕЊА БР.27')
    assert not contradicts("ПРАВНО ПОСЛОВНА ШКОЛА", 'ПРАВНО-ПОСЛОВНА ШКОЛА "ДИМИТРИЈЕ ДАВИДОВИЋ", ТОШИН БУНАР')
    assert not contradicts("", "ГЛАВНА 1") and not contradicts("МЕСНА ЗАЈЕДНИЦА", "ГЛАВНА 1")  # nothing to compare
    # OCR mangled the building a little: the space lost, a letter or two off (Novi Sad 100 and 70, 8 Nov 2026)
    assert not contradicts('ОШ "ЂУРА ДАНИЧИЋ"', "ОШ ЂУРАДАНИЧИЋ , НОВИ САД, ДУШАНАВАСИГbЕВАБР. 19")
    assert not contradicts('ОШ "СВЕТИ САВА"', "ОШ ІІСВЕТИ CABAіІ , РУМЕНКА, ЈОВАНА ЈОВАНОВИЋА ЗМАЈА БР. 24")


def test_reading_split_across_jobs_ends_like_one_run(tmp_path, monkeypatch):
    """The boards workflow reads in parts: a plan lists what to read, each job reads its share, and the merge
    keeps the index and every part in the round's store, complete only when nothing was left."""
    import json

    from izbori import cli
    from izbori.boards import load_store
    records = [index_record(801, 30, "Решење о именовању члана и заменика члана бирачког одбора у проширеном саставу"),
               index_record(802, 31, "Решење о именовању члана и заменика члана бирачког одбора у проширеном саставу"),
               index_record(803, 31, "Решење о именовању члана бирачког одбора у сталном саставу")]

    class Client:
        base = "https://rik.test"

        def get_json(self, path):
            return index_page(records)

    data = tmp_path / "data"
    rnd = data / "rounds" / "680072"
    rnd.mkdir(parents=True)
    (rnd / "meta.json").write_text(json.dumps({"kind": "parliamentary", "date": "2026-10-25",
                                               "contestants": [{"name": "ПРВА ЛИСТА"}]}), encoding="utf-8")
    (data / "rounds.json").write_text(json.dumps({"680072": {"type": 2, "name": "", "kind": "parliamentary"}}),
                                      encoding="utf-8")
    monkeypatch.setattr(cli, "Client", Client)
    monkeypatch.setattr(cli.Archive, "latest_raw", lambda self, rid: None)
    monkeypatch.setattr(cli.Archive, "round_ids", lambda self: ["680072"])

    class Rnd:
        stations = [type("S", (), {"municipality": "Куршумлија", "municipality_code": "70017", "key": f"70017/{n}",
                                   "number": str(n), "name": "ОШ", "district_code": "1"})() for n in (30, 31)]
    monkeypatch.setattr(cli.Archive, "load", lambda self, rid: Rnd())
    plan = tmp_path / "plan.json"
    assert cli.main(["--data", str(data), "boards", "--round", "680072", "--plan", str(plan)]) == 0
    planned = json.loads(plan.read_text(encoding="utf-8"))
    assert [d["id"] for d in planned["todo"]] == ["819801", "819802"] and planned["contestants"]
    assert not (rnd / "boards.json").exists()  # a plan changes no store
    assert not planned["partial"]
    # kept to some municipalities, as to look at one commission's layout: none of theirs here, and partial
    only = tmp_path / "only.json"
    assert cli.main(["--data", str(data), "boards", "--round", "680072", "--plan", str(only), "--only", "71218"]) == 0
    assert json.loads(only.read_text(encoding="utf-8"))["todo"] == []
    assert json.loads(only.read_text(encoding="utf-8"))["partial"]
    # a municipality's decisions already read are read again, once the reading learnt their layout
    (rnd / "boards.json").write_text(json.dumps({"complete": True, "docs": {
        "819801": {"s": "70017/30", "k": "extended", "slots": [[1, True, False]], "u": "/x", "v": PARSER}}}),
        encoding="utf-8")
    again = tmp_path / "again.json"
    assert cli.main(["--data", str(data), "boards", "--round", "680072", "--plan", str(again), "--only", "70017"]) == 0
    assert [d["id"] for d in json.loads(again.read_text(encoding="utf-8"))["todo"]] == ["819802"]
    assert cli.main(["--data", str(data), "boards", "--round", "680072", "--plan", str(again), "--only", "70017",
                     "--reread"]) == 0
    assert [d["id"] for d in json.loads(again.read_text(encoding="utf-8"))["todo"]] == ["819801", "819802"]
    (rnd / "boards.json").unlink()
    # a job reads its share of the plan (none here, with --limit 0) and writes what it read
    out = tmp_path / "part-x.json"
    assert cli.main(["--data", str(data), "boards", "--read", str(plan), "--shard", "1/2", "--out", str(out),
                     "--limit", "0"]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == {"failed": [], "left": 0, "results": {}, "unparsed": 0}
    # two jobs read one decision each; the second ran out of time before its decision
    part0, part1 = tmp_path / "part-0.json", tmp_path / "part-1.json"
    read = {"s": "70017/30", "k": "extended", "r": False, "t": "1793400468", "u": "/x/801.pdf",
            "slots": [[1, True, False]], "unmatched": 0, "addr": "ОШ", "unparsed": False, "station_ok": True}
    part0.write_text(json.dumps({"results": {"819801": read}, "failed": [], "left": 0, "unparsed": 0}),
                     encoding="utf-8")
    part1.write_text(json.dumps({"results": {}, "failed": [], "left": 1, "unparsed": 0}), encoding="utf-8")
    assert cli.main(["--data", str(data), "boards", "--merge", str(plan), str(part0), str(part1)]) == 0
    store = load_store(rnd)
    assert store["docs"]["819801"]["slots"] == [[1, True, False]]
    assert store["docs"]["819803"]["k"] == "standing"
    assert store["docs"]["819803"]["u"].endswith("/803/Решење БМ 31.pdf")
    assert "819802" not in store["docs"] and not store["complete"]  # left for the next run
    part1.write_text(json.dumps({"results": {"819802": {**read, "s": "70017/31"}}, "failed": [], "left": 0,
                                 "unparsed": 0}), encoding="utf-8")
    assert cli.main(["--data", str(data), "boards", "--merge", str(plan), str(part0), str(part1)]) == 0
    assert load_store(rnd)["complete"]


def test_retrying_unreadable_decisions_reaches_past_the_newest_page(tmp_path):
    """With every link kept, a plan reads only the register's newest page; decisions that couldn't be read are
    still listed to read again, by the link kept for them."""
    import json

    from izbori.boards import plan
    (tmp_path / "boards.json").write_text(json.dumps({"complete": True, "docs": {
        "819600": {"s": "70017/12", "k": "extended", "r": False, "t": "1", "u": "/extfile/sr/files/a/600.pdf",
                   "slots": [], "unparsed": True, "v": PARSER},
        "819601": {"s": "70017/13", "k": "extended", "r": False, "t": "1", "u": "/extfile/sr/files/a/601.pdf",
                   "slots": [[1, True, False]], "unparsed": False, "v": PARSER},
        "819602": {"s": "70017/14", "k": "extended", "r": False, "t": "1", "u": "/extfile/sr/files/a/602.pdf",
                   "slots": [[1, True, False]], "unparsed": False}}}), encoding="utf-8")  # read by an older reading

    class Client:
        base = "https://rik.test"

        def get_json(self, path):
            return index_page([])

    planned = plan(tmp_path, "680072", 2, {}, Client(), log=lambda m: None, retry_unparsed=True)
    assert [(d["id"], d["station"], d["url"]) for d in planned["todo"]] == [
        ("819600", "12", "https://www.rik.parlament.gov.rs/extfile/sr/files/a/600.pdf"),
        ("819602", "14", "https://www.rik.parlament.gov.rs/extfile/sr/files/a/602.pdf")]
    # without the retry, only the decision read by the older reading is read again
    assert [d["id"] for d in plan(tmp_path, "680072", 2, {}, Client(), log=lambda m: None)["todo"]] == ["819602"]


def test_odd_stations_name_a_lost_slot():
    """A station lacking a list that almost every other station of its municipality has is listed to look at."""
    from izbori.boards import odd_stations
    lists = lambda *ns: {"lists": {str(n): {"member": True, "deputy": False} for n in ns}}  # noqa: E731
    cov = {f"70513/{i}": lists(1, 2, 3) for i in range(1, 11)}
    cov["70513/4"] = lists(1, 2)  # the Student list's slot lost here
    cov["70513/9"] = lists(1, 2, 3, 7)  # one list more is not odd
    cov["80241/1"] = lists(1)  # too few stations read to say
    assert odd_stations(cov) == {"70513": [("70513/4", [3])]}


def test_garbled_numbers_and_proposals_still_read(contestants):
    """Zrenjanin 1 and Novi Sad 4 (8 Nov 2026): the first slot's number read as letters, and "предлог" garbled in
    a text layer with "подносиоца" intact."""
    a, b, c = LISTS
    text = HEAD + (f"xx, члан Петар Петровић\nзаменик члана __ Марко Марковић\n\nна предлог подносиоца Изборне листе {a};\n"
                   f"2. члан Јован Јовић\n\nзаменик члана Ана Анић\nна xxx подносиоца Изборне листе {b};\n"
                   f"3. члан Лука Лукић\n\nзаменик члана Мина Минић\n\nна предлог подносиоца Изборне листе {c};\n") + TAIL
    assert lists_of(parse_decision(text), contestants) == {1: (True, True), 2: (True, True), 3: (True, True)}
    # the garbage of a bad text layer has numbers and colons but no "члан": not slots
    assert parse_decision("БИРАЧКО МЕСТО БРОЈ 1\n6. xxxx: yyy\n7. zzzz: www на предлог ...").slots == []
