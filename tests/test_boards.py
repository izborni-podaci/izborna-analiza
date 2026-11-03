"""Controllers from board decisions. The fixture is a made-up decision with invented names."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from izbori.boards import (classify, coverage, match_list, municipality_key, parse_decision, parse_index_records,
                           pdf_text)

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def contestants(archive):
    return archive.meta("680072")["contestants"]


def test_parse_decision_text():
    d = parse_decision((FIX / "board_decision.txt").read_text(encoding="utf-8"))
    assert d.station == "12"
    assert d.address == 'ОШ "ВУК КАРАЏИЋ", ПРИМЕР, ГЛАВНА 1'
    assert [(s.member, s.deputy) for s in d.slots] == [(True, True), (False, False), (True, False), (True, False)]


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


def test_classify():
    assert classify("РЕШЕЊЕ О ИМЕНОВАЊУ ЧЛАНОВА ... У ПРОШИРЕНОМ САСТАВУ БМ 77", "") == ("extended", False)
    assert classify("БМ 11", "Решење о именовању члана и заменика члана бирачког одбора у проширеном саставу") \
        == ("extended", False)
    assert classify("РЕШЕЊЕ", "Решење о именовању члана ... у проширеном саставу – поновно гласање") == ("extended", True)
    assert classify("РЕШЕЊЕ О ИМЕНОВАЊУ ... У СТАЛНОМ САСТАВУ", "Решење ... у проширеном саставу")[0] == "extended"
    assert classify("РЕШЕЊЕ О ИМЕНОВАЊУ ПРЕДСЕДНИКА ... У СТАЛНОМ САСТАВУ", "")[0] == "standing"
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
