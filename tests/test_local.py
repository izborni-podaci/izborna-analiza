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


def test_classify_skips_a_site_that_does_not_answer(tmp_path):
    import json
    docs = {f"https://www.bac.rs/{i}.pdf": {"m": "80055", "k": "boards", "seen": "x"} for i in range(12)}
    docs.update({f"https://p.rs/{i}.pdf": {"m": "80314", "k": "boards", "seen": "x"} for i in range(3)})
    (tmp_path / "municipal_docs.json").write_text(json.dumps({"docs": docs}), encoding="utf-8")
    asked = []

    def one(url):
        asked.append(url)
        if "bac.rs" in url:
            return url, None, "TimeoutError"
        return url, local.classify("ЗАПИСНИК О РАДУ БИРАЧКОГ ОДБОРА"), None
    logged = []
    assert local.run_classify(tmp_path, None, log=logged.append, workers=1, one=one) == 3
    assert sum("bac.rs" in u for u in asked) == local.SITE_DOWN
    assert any("{'bac.rs': 7}" in line for line in logged)
    # the next run asks again
    asked.clear()
    local.run_classify(tmp_path, None, log=lambda *_: None, workers=2, one=one)
    assert sum("bac.rs" in u for u in asked) >= local.SITE_DOWN


def test_classify_shards_split_by_municipality_and_merge(tmp_path):
    import json
    import shutil
    docs = {f"https://{m}.rs/{i}.pdf": {"m": m, "k": "boards", "seen": "x"}
            for m, n in (("80314", 5), ("70017", 3), ("80446", 2), ("80373", 1)) for i in range(n)}
    where = local.shard_of(sorted(docs), docs, 2)
    assert where == {"80314": 0, "70017": 1, "80446": 1, "80373": 0}  # 6 and 5 documents
    (tmp_path / "municipal_docs.json").write_text(json.dumps({"docs": docs}), encoding="utf-8")

    def one(url):
        return url, local.classify("ЗАПИСНИК О РАДУ БИРАЧКОГ ОДБОРА"), None
    parts = []
    for i in range(2):
        d = tmp_path / f"shard{i}"
        d.mkdir()
        shutil.copy(tmp_path / "municipal_docs.json", d)
        assert local.run_classify(d, None, log=lambda *_: None, workers=1, one=one, shard=(i, 2)) == (6, 5)[i]
        parts.append(d / local.STORE)
    assert local.merge_parts(tmp_path, parts) == 11
    assert set(local.load_store(tmp_path)["docs"]) == set(docs)
    assert local.merge_parts(tmp_path, parts) == 0


def test_merge_keeps_each_shards_new_entries_whatever_the_order(tmp_path):
    import json
    old = {"m": "80314", "k": "boards", "e": None, "d": None}  # an entry of an older version (no "v")
    base = {"https://p.rs/a.pdf": old, "https://t.rs/b.pdf": {**old, "m": "80446"}}
    new_p = {**old, "k": "minutes", "v": local.CLASSIFIER}
    new_t = {**old, "m": "80446", "k": "lists", "v": local.CLASSIFIER}
    parts = []
    for i, store in enumerate(({**base, "https://p.rs/a.pdf": new_p},  # each part: the whole store, plus its own
                               {**base, "https://t.rs/b.pdf": new_t})):
        parts.append(tmp_path / f"part{i}.json")
        parts[-1].write_text(json.dumps({"docs": store}), encoding="utf-8")
    (tmp_path / local.STORE).write_text(json.dumps({"docs": base}), encoding="utf-8")
    assert local.merge_parts(tmp_path, parts) == 2
    assert local.load_store(tmp_path)["docs"] == {"https://p.rs/a.pdf": new_p, "https://t.rs/b.pdf": new_t}
    assert local.merge_parts(tmp_path, parts[::-1]) == 0


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


def test_a_station_ocr_lost_comes_back_with_every_figure(tmp_path):
    (tmp_path / "local_corrections.csv").write_text(
        "round,station,registered,voted,ballots,invalid,valid,votes,note\n"
        "L1-1,9,305,160,160,3,157,86 32 10 1 28,Claude\n"
        "L1-1,10,,,,,,1 2 3 4 5,a few figures only\n", encoding="utf-8")
    k, rows, aside = local.result_rows(TABLE)
    logged = []
    rows, aside = local.corrected(tmp_path, "L1-1", rows, aside, logged.append)
    assert rows[-1]["n"] == 9 and rows[-1]["registered"] == 305 and rows[-1]["v"] == [86, 32, 10, 1, 28]
    assert any("station 10: no such row" in m for m in logged)


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


def test_overview_groups_a_municipality_s_documents_by_time(tmp_path):
    import json
    (tmp_path / "municipal_sites.csv").write_text("municipality_code,name,domain,note\n80373,Сечањ,s.rs,x\n",
                                                  encoding="utf-8")
    docs = {f"https://s.rs/2025/11/BM-{n}.pdf": {"m": "80373", "k": "boards", "e": "local", "d": "2025-11-19"}
            for n in range(5)}
    docs.update({"https://s.rs/2025/12/Ukupan-izvestaj.pdf": {"m": "80373", "k": "results", "e": "local", "d": "2025-12-21"},
                 "https://s.rs/2025/11/BIRACKO-MESTO-1.pdf": {"m": "80373", "k": "minutes", "e": "local", "d": None},
                 "https://s.rs/2020/06/a.pdf": {"m": "80373", "k": "lists", "e": "local", "d": "2020-06-02"}})
    (tmp_path / local.STORE).write_text(json.dumps({"docs": docs}), encoding="utf-8")
    (tmp_path / "rounds" / "L80373-20251130").mkdir(parents=True)
    rows = local.overview(tmp_path, log=lambda *a: None, fetch=lambda u: b"", read=True)
    assert len(rows) == 1 and rows[0]["first"] == "2025-11-19" and rows[0]["last"] == "2025-12-21"
    assert rows[0]["results"] == "totals" and rows[0]["boards"] == 5 and rows[0]["undated_minutes"] == 1
    assert rows[0]["published"] == ["L80373-20251130"]


def test_strokes_taken_as_the_one_combination_that_adds_up():
    text = """ИЗВЕШТАЈ
1 350 210 210 2 208 94 29 8 2 4 10 61
2 500 284 284 4 280 171 17 24 16 | 10 31
3 89 22 22 0 22 16 1 0 || 0 1 3
4 74 45 43 0 43 34 3 2 0 2 || ||
5 61 33 33 0 38 31 2 0 0 0 0 0
"""
    k, rows, aside = local.result_rows(text)
    by = {r["n"]: r for r in rows}
    assert by[2]["v"][4] == 11 and "list 5 read as strokes" in by[2]["note"]
    assert by[3]["v"][3] == 1
    assert by[4]["v"][5:] == [1, 1] and "lists 6, 7" in by[4]["note"]
    assert [a["n"] for a in aside] == [5]  # no strokes to take: set aside
    assert local.bars_solved(["1", "|", "|"], [1, 1, 1], 13) is None  # 1+1+11 and 1+11+1: two ways


SECTIONS = """ИЗВЕШТАЈ О РЕЗУЛТАТИМА ГЛАСАЊА ЗА СВАКО БИРАЧКО МЕСТО
1 Бирачко место број 1 у "Дом", улица број 38.
1) Број бирача уписаних у бирачки списак- 213
2) Број бирача који су гласали - 144
3) Број неважећих гласачких листића - 29
4) Број важећих гласачких листића- 115
5) Број гласова и број мандата које је добила свака изборна листа:
Редни Назив изборне листе Број гласова
1 2 3
Прва листа – са дугим
називом 95
Друга листа 20

2 Бирачко место број 2 у школи,
број 172
1)Број бирача уписаних у бирачки списак- 398
2)Број бирача који су гласали - 269
3)Број неважећих гласачких листића - 96
4)Број важећих гласачких листића- 173
1 2 3
Прва листа 136
Друга листа 37

3. Бирачко место бр.3 , Село:
-Број уписаних бирача: 208
-Број бирача који су гласали: 185
- Број неупотребљених: 23
- Број неважећих гласачких листића: 16
- Број важећих гласачких листића: 169
1 100
Прва листа
2 | Друга листа 70
"""


def test_a_report_with_a_section_per_station():
    k, rows, aside = local.result_rows(SECTIONS)
    assert k == 2
    assert rows[0] == {"n": 1, "registered": 213, "voted": 144, "ballots": 144, "invalid": 29, "valid": 115,
                       "v": [95, 20], "note": "ballots taken as valid and invalid (the report has none)"}
    assert rows[1]["v"] == [136, 37]
    assert aside == [{"n": 3, "why": "lists add up to 170, valid votes read 169",
                      "raw": {"n": 3, "registered": 208, "voted": 185, "invalid": 16, "valid": 169, "v": [100, 70]}}]


def test_report_pages_end_above_the_signatures(tmp_path):
    import json
    for line in ("Број: 013-67/2023-01", "ПРЕДСЕДНИК", "Predsednica komisije", "ЗАМЕНИК ПРЕДСЕДНИКА", "М.П."):
        assert local.PAGE_END.search(line), line
    for line in ("1 350 210 210 2 208 94 29 8 2 4 10 61", "4) Број важећих гласачких листића- 115",
                 "Број бирача уписаних у бирачки списак 35.951"):
        assert not local.PAGE_END.search(line), line
    (tmp_path / "municipal_docs.json").write_text(json.dumps({"docs": {
        "https://r.rs/Ukupan-izvestaj-po-birackim-mestima.pdf": {"m": "71013", "k": "x", "seen": "x"},
        "https://r.rs/Resenje.pdf": {"m": "71013", "k": "x", "seen": "x"}}}), encoding="utf-8")
    asked = []

    def fetch(u):
        asked.append(u)
        raise OSError
    assert local.run_pages(tmp_path, "71013", "po-birackim", tmp_path / "out", log=lambda *_: None, fetch=fetch) == 0
    assert asked == ["https://r.rs/Ukupan-izvestaj-po-birackim-mestima.pdf"]


def test_a_sideways_page_is_turned_by_tesseract_s_orientation():
    from izbori import boards
    osd = "Page number: 0\nOrientation in degrees: 90\nRotate: 270\nOrientation confidence: 7.76\nScript: Cyrillic\n"
    assert boards.rotation(osd) == 270
    assert boards.rotation(osd.replace("7.76", "0.40")) == 0  # not sure enough: left as it is
    assert boards.rotation("Rotate: 0\nOrientation confidence: 9.1") == 0


def test_a_table_s_lines_are_taken_out(tmp_path):
    import pytest
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    from izbori import boards
    img = np.full((400, 900), 255, np.uint8)
    for y in (50, 150, 250, 350):
        cv2.line(img, (20, y), (880, y), 0, 2)
    for x in (20, 300, 600, 880):
        cv2.line(img, (x, 50), (x, 350), 0, 2)
    cv2.putText(img, "1534", (60, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, 0, 3)
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), img)
    boards.unruled(path)
    out = cv2.imread(str(path), 0)
    assert out[50, 450] == 255 and out[200, 300] == 255  # the lines are gone
    assert (out[80:125, 60:200] < 128).sum() > 200  # the figure stays


def test_links_as_they_can_be_asked_for():
    assert local.fetch_url("https://www.kanjiza.rs/data\\files\\docs\\izbori2024\\a.pdf") == \
        "https://www.kanjiza.rs/data/files/docs/izbori2024/a.pdf"
    assert local.fetch_url("https://p.rs/Решење.pdf?lang=lat").endswith("%D0%B5.pdf?lang=lat")


PROKUPLJE_TOTALS = """ЗБИРНИ ИЗВЕШТАЈ
1. Број бирача уписаних у бирачки списак 35.951
2. Број бирача који је изашао на изборе 21.812
3. Број бирача који су гласали 21.809
4. Број неважећих гласачких листића 575
5. Број важећих гласачких листића 21.234
6. Број и проценат гласова које је добила свака изборна листа:
12.488 57,26%
1. ПРВА ЛИСТА
1.819 8,34%
2. ДРУГА ЛИСТА
1.212 5,56%
537 2,46%
610 2,8%
859 3,49%
3.709 17,01%
Члан 2.
"""
ZEMUN_TOTALS = """4. Број бирача уписаних у бирачки списак 169.069
5. Број и проценат бирача који су изашли на изборе 77,463 (45,82%)
6. Број гласачких листића који нису убачени у гласачке кутије 48
7. Број бирача који су гласали 77. 415
8. Број и проценат неважећих гласачких листића 1.770 (2,29%)
9. Број и проценат важећих гласачких листића 75.645 (97,71%)
1 ПРВА 43,122 55.70 35 61.40
2 ДРУГА 1,899 2.45 0 0.00
3 ТРЕЋА 1,309 1.69 0 0.00
4 ЧЕТВРТА 16,942 21.88 14 24.56
5 ПЕТА 1,039 1.34 0 0.00
6 ШЕСТА 1,078 1.39 1 1.75
7 СЕДМА 2,777 3.59 2 3.51
8 ОСМА 6,316 8.16 5 8.77
9 ДЕВЕТА 1,163 1.50 0 0.00
"""


def test_the_commission_s_totals():
    t = local.totals_of(PROKUPLJE_TOTALS)
    assert t == {"registered": 35951, "out": 21812, "voted": 21809, "invalid": 575, "valid": 21234,
                 "v": [12488, 1819, 1212, 537, 610, 859, 3709]}
    z = local.totals_of(ZEMUN_TOTALS, 9)
    assert (z["registered"], z["out"], z["voted"], z["invalid"], z["valid"]) == (169069, 77463, 77415, 1770, 75645)
    assert z["v"] == [43122, 1899, 1309, 16942, 1039, 1078, 2777, 6316, 1163]
    assert local.totals_of(SECTIONS) is None  # a report by station's sections holds no totals
    rows = [{"registered": 35951, "voted": 21812, "ballots": 21809, "invalid": 575, "valid": 21234,
             "v": [12488, 1819, 1212, 537, 610, 859, 3709]}]
    assert local.check_totals(rows, t) == {"matches": True, "differs": {}}
    rows[0]["v"] = [12388, 1919, 1212, 537, 610, 859, 3709]  # two lists swapped a hundred: the rows add up, not the lists
    assert local.check_totals(rows, t)["differs"] == {"v": [rows[0]["v"], t["v"]]}
    assert local.check_totals(rows, t)["over"] == [2]  # list 2 already more than its total: misread somewhere
    assert local.check_totals(rows, None)["matches"] is False


def test_a_report_found_twice_is_read_once():
    store = {"docs": {"https://bac.rs/a/izvestaj.pdf": {"m": "80055", "e": "local", "d": "2024-06-06"},
                      "https://www.bac.rs/a/izvestaj.pdf": {"m": "80055", "e": "local", "d": "2024-06-06"}}}
    assert local.report_candidates(store, "80055", "2024-06-02") == ["https://bac.rs/a/izvestaj.pdf"]


def test_a_link_s_variants():
    assert local.link_variants("https://g.rs/2020/05/SOG 1.docx?lang=lat") == [
        "https://g.rs/2020/05/SOG 1.docx?lang=lat", "https://g.rs/2020/05/SOG 1.docx", "https://g.rs/2020/05/SOG-1.docx"]
    assert local.link_variants("https://g.rs/a.pdf") == ["https://g.rs/a.pdf"]


def test_totals_with_spaces_between_thousands():
    t = local.totals_of("2. БРОЈ БИРАЧА УПИСАНИХ У БИРАЧКИ СПИСАК: 22 901\n3. БРОЈ БИРАЧА КОЈИ ЈЕ ИЗАШАО НА ИЗБОРЕ 16 457\n"
                        "4. БРОЈ ГЛАСАЧКИХ ЛИСТИЋА КОЈИ СЕ НАЛАЗЕ У ГЛАСАЧКИМ КУТИЈАМА: 16 454\n"
                        "5. БРОЈ НЕВАЖЕЋИХ ГЛАСАЧКИХ ЛИСТИЋА: 429\n6. БРОЈ ВАЖЕЋИХ ГЛАСАЧКИХ ЛИСТИЋА: 16 025\n")
    assert (t["registered"], t["out"], t["invalid"], t["valid"]) == (22901, 16457, 429, 16025)
