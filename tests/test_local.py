"""Local elections from the municipalities' documents: the probe shows forms' words and numbers, never a name."""
from izbori import local


def test_shape_masks_everything_but_the_forms_words():
    text = "ЗАПИСНИК о раду бирачког одбора\nМарко Марковић, члан, на предлог 3. Српска напредна странка 1.234 гласова"
    out = local.shape(text)
    assert "Марко" not in out and "Марковић" not in out and "Српска" not in out
    assert "ЗАПИСНИК" in out and "члан" in out and "1.234" in out and "гласова" in out


def test_probe_logs_folders_and_masked_layouts():
    docs = {"https://p.rs/up/2023/12/Resenje-BO-BM-1.pdf": {"m": "80314", "k": "boards", "seen": "x"},
            "https://p.rs/up/2023/11/Zapisnik.pdf": {"m": "80314", "k": "commission", "seen": "x"},
            "https://q.rs/a.pdf": {"m": "70017", "k": "boards", "seen": "x"}}
    logged = []
    local.probe(docs, "80314", kind="boards", log=logged.append, fetch=lambda u: b"PK not a docx")
    assert logged[0].startswith("80314: 1 documents of kind boards; by folder: /up/2023/12 1")
    assert len(logged) == 2  # the one document, which failed to read as a .docx


def test_the_command_runs(tmp_path):
    from izbori import cli
    assert cli.main(["--data", str(tmp_path), "local", "--probe", "80314"]) == 0


def test_classify_by_the_forms_words():
    c = local.classify
    assert c("ЗАПИСНИК О РАДУ БИРАЧКОГ ОДБОРА на изборима за народне посланике одржаних 25. октобра 2026") == \
        {"k": "minutes", "e": "parliamentary", "d": "2026-10-25", "v": local.CLASSIFIER}
    assert c("ИЗВЕШТАЈ О УКУПНИМ РЕЗУЛТАТИМА ИЗБОРА за одборнике Скупштине града одржаних 17.12.2023. године") == \
        {"k": "results", "e": "local", "d": "2023-12-17", "v": local.CLASSIFIER}
    assert c("Р Е Ш Е Њ Е о именовању чланова бирачког одбора за изборе за одборнике, расписане за 2. јун 2024")["k"] == "boards"
    assert c("ЗАПИСНИК са 16. седнице Изборне комисије")["k"] == "session"
    assert c("ОДЛУКА о одређивању бирачких места за изборе за посланике у Скупштину Аутономне покрајине Војводине") == \
        {"k": "stations", "e": "provincial", "d": None, "v": local.CLASSIFIER}
    assert c("Јавни позив")["k"] == "other"


def test_classify_run_keeps_kinds_only_and_resumes(tmp_path):
    import json
    (tmp_path / "municipal_docs.json").write_text(json.dumps({"docs": {
        "https://p.rs/a.pdf": {"m": "80314", "k": "boards", "seen": "x"},
        "https://p.rs/b.pdf": {"m": "80314", "k": "commission", "seen": "x"},
        "https://q.rs/c.pdf": {"m": "70017", "k": "boards", "seen": "x"}}}), encoding="utf-8")
    pages = {"https://p.rs/a.pdf": "ЗАПИСНИК О РАДУ БИРАЧКОГ ОДБОРА", "https://p.rs/b.pdf": None}

    def one(url):
        t = pages[url]
        return (url, local.classify(t), None) if t else (url, None, "URLError")
    assert local.run_classify(tmp_path, {"80314"}, log=lambda *_: None, workers=1, one=one) == 1
    store = local.load_store(tmp_path)
    assert store["docs"] == {"https://p.rs/a.pdf": {"m": "80314", "k": "minutes", "e": None, "d": None,
                                                    "v": local.CLASSIFIER}}
    pages["https://p.rs/b.pdf"] = "ЗАПИСНИК са седнице"
    assert local.run_classify(tmp_path, {"80314"}, log=lambda *_: None, workers=1, one=one) == 1  # only b, now


TABLE = """ИЗВЕШТАЈ О РЕЗУЛТАТИМА ИЗБОРА ЗА ОДБОРНИКЕ
1 1354 577 577 14 563 473 5 37 9 39
2 1201 600 600 17 583 483 3 56 15 26
||| 1636 867 867 24 843 682 9 65 37 50
4 1483 629 629 16 613 397 3 174 1! 28
5 1898 1033 1032 |90 942 794 10 44 18 76
6 878 37 377 7 370 231 3 70 14 52
37 1252 552 552 10 542 333 6 102 xx 90
8 1488 684 684 30 654 534 3 51 14 46
Број: 1-01-013-1/2024
"""


def test_result_rows_check_themselves():
    k, rows, aside = local.result_rows(TABLE)
    assert k == 5
    by = {r["n"]: r for r in rows}
    assert by[3]["v"] == [682, 9, 65, 37, 50]  # "|||" is the sequence's 3
    assert by[4]["v"][3] == 11  # "1!"
    assert by[5]["invalid"] == 90 and "invalid" in by[5]["note"]  # "|90" read 190: 1032 − 942
    assert by[6]["voted"] == 377 and "voted taken as the ballots" in by[6]["note"]  # "37": a digit lost
    assert by[7]["v"][3] == 11 and "list 4 from the valid votes" in by[7]["note"]  # unreadable, the sum gives it
    assert [(a["n"], a["why"]) for a in aside] == [(8, "lists add up to 648, valid votes read 654")]  # never guessed


def test_list_names_from_proclamations():
    m = local.LIST_NAME.search("РЕШЕЊЕ о проглашењу изборне листе „ПРИМЕР – ЗА ГРАД“ коју је поднела")
    assert m.group(1) == "ПРИМЕР – ЗА ГРАД"


def test_a_person_s_reading_brings_a_row_back(tmp_path):
    (tmp_path / "local_corrections.csv").write_text(
        "round,station,registered,voted,ballots,invalid,valid,votes,note\n"
        "L1-1,8,,,,,,534 3 57 14 46,Marko\n"
        "L1-1,2,,,,,,483 3 56 15 99,wrong\n", encoding="utf-8")
    k, rows, aside = local.result_rows(TABLE)
    logged = []
    rows, aside = local.corrected(tmp_path, "L1-1", rows, aside, logged.append)
    assert aside == [] and rows[-1]["n"] == 8 and rows[-1]["v"] == [534, 3, 57, 14, 46]
    assert rows[-1]["note"] == "checked by hand against the report (Marko)"
    assert rows[1]["v"] == [483, 3, 56, 15, 26]  # a correction that doesn't add up changes nothing
    assert any("station 2 doesn't add up" in m for m in logged)


LISTS = [{"name": "Александар Вучић – Панчево сутра", "rik_name": "АЛЕКСАНДАР ВУЧИЋ – ПАНЧЕВО СУТРА", "short": "Панчево сутра"},
         {"name": "Савез војвођанских Мађара – др Балинт Пастор", "rik_name": "", "short": "СВМ"},
         {"name": "Панчево против насиља – Бирам борбу", "rik_name": "", "short": "Панчево против насиља"},
         {"name": "Панчево – борба против насиља (Покрет обнове Краљевине Србије, Народна странка)", "rik_name": "",
          "short": "Борба против насиља (ПОКС)"},
         {"name": "Група грађана Панчевачка група – Ваше комшије", "rik_name": "", "short": "Панчевачка група"}]
# Pančevo's layout of 2024, with invented people
EXTENDED = """На основу члана 25. Закона, Изборна комисија града Панчева, на седници 22. маја 2024. године, донела је

РЕШЕЊЕ

О ИМЕНОВАЊУ ПРЕДСЕДНИКА И ЧЛАНОВА БИРАЧКОГ ОДБОРА
- У ПРОШИРЕНОМ САСТАВУ -
ЗА СПРОВОЂЕЊЕ ИЗБОРА ЗА ОДБОРНИКЕ СКУПШТИНЕ ГРАДА ПАНЧЕВА
ЗА БИРАЧКО МЕСТО БРОЈ 7 У ПАНЧЕВУ

ОШ „Мика Мишић“ Панчево, Улица Нова бр.1

1. У бирачки одбор у проширеном саставу именују се:

1. члан: Пера Перић, Панчево, Александар Вучић-Панчево сутра;

- заменик 1. члана:Жика Жикић, Панчево, Александар Вучић-Панчево
сутра;

2. члан: Мика Микић, Панчево, Панчево против насиља – Бирам борбу!

- заменик 2. члана: Лаза Лазић, Старчево, Панчево против насиља – Бирам борбу;

3. члан: Ана Анић, Панчево, ГГ: "Панчевачка група – Ваше комшије!"

- заменик 3. члана: ____________

2. Ово решење објавити на сајту.
"""


def test_extended_board_from_pancevo_s_layout():
    slots, unmatched = local.board_slots(EXTENDED, LISTS)
    assert slots == [[1, True, True], [3, True, True], [5, True, False]] and unmatched == 0
    got = local.read_board(EXTENDED, "https://x/BM-7.pdf", "2024-05-22", LISTS, {"7"}, "80314")
    assert got["s"] == "80314/7" and got["k"] == "extended" and got["slots"] == slots and not got["unparsed"]
    assert "Пера" not in str(got) and got["u"] == "https://x/BM-7.pdf"
    assert local.read_board(EXTENDED, "u", None, LISTS, {"8"}, "80314") is None  # not a station of the round


def test_changes_and_minutes_are_kept_as_links_or_left():
    change = EXTENDED.replace("О ИМЕНОВАЊУ", "О ИЗМЕНИ РЕШЕЊА О ИМЕНОВАЊУ")
    got = local.read_board(change, "u", "2024-05-30", LISTS, {"7"}, "80314")
    assert got["k"] == "extended_change" and "slots" not in got
    standing = EXTENDED.replace("ПРОШИРЕНОМ", "СТАЛНОМ")
    assert local.read_board(standing, "u", "", LISTS, {"7"}, "80314")["k"] == "standing"
    minutes = EXTENDED.replace("РЕШЕЊЕ", "ЗАПИСНИК О РАДУ")
    assert local.read_board(minutes, "u", "", LISTS, {"7"}, "80314") is None


def test_read_boards_writes_the_round_s_store(tmp_path):
    import json
    rdir = tmp_path / "rounds" / "L80314-20240602"
    rdir.mkdir(parents=True)
    (rdir / "meta.json").write_text(json.dumps({"date": "2024-06-02", "contestants": LISTS,
                                                "local": {"municipality": "80314"}}), encoding="utf-8")
    (rdir / "results.csv").write_text("bm_uid,bm_broj\nx,7\n", encoding="utf-8")
    (tmp_path / local.STORE).write_text(json.dumps({"docs": {
        "https://x/BM-7.pdf": {"m": "80314", "k": "lists", "e": "local", "d": "2024-05-22"},
        "https://x/old.pdf": {"m": "80314", "k": "boards", "e": "local", "d": "2022-03-01"},
        "https://x/z.pdf": {"m": "80314", "k": "minutes", "e": "local", "d": "2024-06-02"}}}), encoding="utf-8")
    seen = []

    def one(item):
        seen.append(item[0])
        return item[0], local.read_board(EXTENDED, item[0], item[1], item[2], item[3], item[4]), None
    s = local.read_boards(tmp_path, "L80314-20240602", log=lambda *a: None, workers=1, one=one)
    assert seen == ["https://x/BM-7.pdf"]
    assert s["per_list"] == {"1": 1, "2": 0, "3": 1, "4": 0, "5": 1} and s["stations_read"] == 1
    from izbori import boards
    cov = boards.coverage(boards.load_store(rdir))
    assert cov["80314/7"]["lists"]["5"] == {"member": True, "deputy": False}


def test_role_shape_shows_only_the_lists_words():
    lines = local.role_shape(EXTENDED, LISTS)
    assert len(lines) == 6 and lines[0].endswith("-> 1") and "Пера" not in " ".join(lines)
    assert "Перић" not in " ".join(lines) and "Панчевачка" in lines[4]


GARBLED = EXTENDED.replace("2. Ово решење", """4. чпан; Ива Ивић, Омољица, ПОКС: "Панчево-Борба против насиља!"
~ замсник 4. чпана: Јова Јовић, Панчево, ПОКС: "Панчево-Борба против насиља!".

2. Ово решење""").replace('ГГ: "Панчевачка група – Ваше комшије!"', 'Група грађана "ГРУПА ПАНЧЕВО"')


def test_roles_read_through_ocr_and_other_names_of_the_lists():
    slots, unmatched = local.board_slots(GARBLED, LISTS)
    assert slots == [[1, True, True], [3, True, True], [4, True, True], [5, True, False]] and unmatched == 0
    others = [dict(c, name="Група грађана " + c["name"]) for c in LISTS]  # two citizens' groups: not guessed
    assert local.role_list('Ана Анић, Панчево, Група грађана "ГРУПА ПАНЧЕВО"', others) is None
    assert local.role_list("Ана Анић, Панчево, Панчево против насиља", LISTS) is None  # lists 3 and 4 alike


def test_a_supplement_s_quoted_role_and_lists_told_by_their_own_words():
    supplement = EXTENDED.split("1. У бирачки")[0] + '1. Допуњује се решење:\n\n„- заменик 5. члана: Ана Анић, Панчево, Група грађана "ГРУПА ПАНЧЕВО".“\n\n2. Ово решење'
    assert local.board_slots(supplement, LISTS) == ([[5, False, True]], 0)
    assert local.role_list("Пера Перић, Панчево, Савез војвођ- анских Мађара", LISTS) == 2
    assert local.role_list("Пера Перић, Омољица, Савез", LISTS) is None  # one word only
    assert local.role_list("Пера Перић, Панчево, xxx насиља!", LISTS) is None  # lists 3 and 4 alike
    # a line ending in a word before the next member's number is not a deputy's role
    text = EXTENDED.replace("Александар Вучић-Панчево\nсутра;", "Александар Вучић-Панчево;\nсутра\n")
    assert local.board_slots(text, LISTS)[0][0] == [1, True, True]


def test_report_candidates_by_link_and_days_after():
    store = {"docs": {"https://x/2025/12/Ukupan-izvestaj.pdf": {"m": "80373", "k": "lists", "e": "local", "d": "2025-12-21"},
                      "https://x/2022/04/Ukupni-izvestaj.pdf": {"m": "80373", "k": "other", "e": "local", "d": "2022-04-06"},
                      "https://x/Zbirni-izvestaj-poslanici.pdf": {"m": "80373", "k": "results", "e": "parliamentary", "d": "2025-12-01"},
                      "https://x/Resenje.pdf": {"m": "80373", "k": "results", "e": "local", "d": "2025-12-01"}}}
    assert local.report_candidates(store, "80373", "2025-11-30") == ["https://x/2025/12/Ukupan-izvestaj.pdf"]


def test_the_results_section_alone_is_cut_out():
    page = ([("ЗАПИСНИК", 50, 80, 800), ("1. Број бирачког места 1", 120, 150, 800),
             ("4. БРОЈ БИРАЧА КОЈИ СУ УПИСАНИ У ИЗВОД 546", 400, 430, 800), ("11. РЕЗУЛТАТИ ГЛАСАЊА", 900, 930, 600),
             ("11.1 БРОЈ БИРАЧА 465", 950, 980, 800), ("11.5 БРОЈ ГЛАСОВА", 1300, 1330, 800),
             ("III. БИРАЧКИ ОДБОР", 1700, 1730, 600), ("ПРЕДСЕДНИК", 1750, 1780, 600)], 2339, 1654)
    assert local.result_regions([page]) == [(0, 340, 570, 0, 1654), (0, 885, 1695, 0, 1654)]
    # two pages side by side: the left one's parts don't end the right one's results; they run on to the next scan
    spread = ([("I. ПРЕ ОТВАРАЊА", 300, 330, 800), ("1. Број бирачког места", 400, 430, 800),
               ("III. РЕЗУЛТАТИ ГЛАСАЊА", 20, 50, 2500), ("10.1 БРОЈ БИРАЧА", 80, 110, 2500)], 2339, 3306)
    nxt = ([("листа 4 422", 100, 130, 800), ("ЧЛАН", 600, 630, 800)], 2339, 3306)
    assert local.result_regions([spread, nxt]) == [(0, 5, 2339, 1653, 3306), (1, 0, 595, 0, 1653)]
    assert local.result_regions([([("ЗАПИСНИК", 50, 80, 800)], 2339, 1654)]) == []
    assert local.safe_stem("https://t.rs/upload/ЗАПИСНИК О РАДУ БИРАЧКОГ ОДБОРА ЛО1.pdf") == "zapisnik-o-radu-birackog-odbora-lo1"


def test_crops_command_runs(tmp_path):
    from izbori import cli
    assert cli.main(["--data", str(tmp_path), "local", "--crops", "80446", "--out", str(tmp_path / "c")]) == 0


def test_hand_rows_must_add_up(tmp_path):
    (tmp_path / local.HAND).write_text(
        "round,station,registered,voted,ballots,invalid,valid,votes,source,note\n"
        "L1-20240602,1,546,316,316,4,312,200 50 40 22,https://t.rs/LO1.pdf,\n"
        "L1-20240602,2,600,300,300,5,290,200 50 40 0,https://t.rs/LO2.pdf,\n"
        "L9-20240602,1,1,1,1,0,1,1,x,\n", encoding="utf-8")
    k, rows, aside, links = local.hand_rows(tmp_path, "L1-20240602", log=lambda *a: None)
    assert k == 4 and [r["n"] for r in rows] == [1] and aside[0]["n"] == 2 and links[1] == "https://t.rs/LO1.pdf"


def test_the_title_decides_before_the_page():
    c = local.classify
    pre = "На основу члана 25. Закона о локалним изборима, Изборна комисија града Панчева донела је\n\n"
    # an extended board names the lists it seats: still a board
    ext = pre + ("РЕШЕЊЕ\nО ИМЕНОВАЊУ ЧЛАНОВА БИРАЧКОГ ОДБОРА У ПРОШИРЕНОМ САСТАВУ ЗА ИЗБОРЕ ЗА ОДБОРНИКЕ\n"
                 "1. члан: …, на предлог изборне листе АЛЕКСАНДАР ВУЧИЋ – ПАНЧЕВО СУТРА, збирна изборна листа")
    assert c(ext)["k"] == "boards" and c(ext)["v"] == local.CLASSIFIER
    # a report of results, whose page goes on to name every list
    rep = pre + "УКУПНИ ИЗВЕШТАЈ\nна основу збирне изборне листе\nО РЕЗУЛТАТИМА ИЗБОРА ЗА ОДБОРНИКЕ СКУПШТИНЕ ОПШТИНЕ"
    assert c(rep)["k"] == "results"
    # an appointment to the municipal commission, on a list's proposal, is neither a result nor a board
    oik = pre + ("РЕШЕЊЕ о именовању члана и заменика члана у проширени састав Општинске изборне комисије на "
                 "предлог подносиоца изборне листе, ради утврђивања резултата избора")
    assert c(oik)["k"] == "commission"
    assert c("R E Š E N J E o imenovanju članova biračkog odbora")["k"] == "boards"


def test_an_older_classification_is_read_again(tmp_path):
    import json
    (tmp_path / "municipal_docs.json").write_text(json.dumps({"docs": {
        "https://p.rs/a.pdf": {"m": "80314", "k": "boards", "seen": "x"},
        "https://p.rs/b.pdf": {"m": "80314", "k": "boards", "seen": "x"}}}), encoding="utf-8")
    (tmp_path / local.STORE).write_text(json.dumps({"docs": {
        "https://p.rs/a.pdf": {"m": "80314", "k": "lists", "e": "local", "d": None},
        "https://p.rs/b.pdf": {"m": "80314", "k": "minutes", "e": None, "d": None, "v": local.CLASSIFIER}}}),
        encoding="utf-8")
    seen = []

    def one(url):
        seen.append(url)
        return url, local.classify("РЕШЕЊЕ о именовању бирачког одбора"), None
    assert local.run_classify(tmp_path, None, log=lambda *_: None, workers=1, one=one) == 1
    assert seen == ["https://p.rs/a.pdf"] and local.load_store(tmp_path)["docs"]["https://p.rs/a.pdf"]["k"] == "boards"
