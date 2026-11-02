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
