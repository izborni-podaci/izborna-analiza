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
        {"k": "minutes", "e": "parliamentary", "d": "2026-10-25"}
    assert c("ИЗВЕШТАЈ О УКУПНИМ РЕЗУЛТАТИМА ИЗБОРА за одборнике Скупштине града одржаних 17.12.2023. године") == \
        {"k": "results", "e": "local", "d": "2023-12-17"}
    assert c("Р Е Ш Е Њ Е о именовању чланова бирачког одбора за изборе за одборнике, расписане за 2. јун 2024")["k"] == "boards"
    assert c("ЗАПИСНИК са 16. седнице Изборне комисије")["k"] == "session"
    assert c("ОДЛУКА о одређивању бирачких места за изборе за посланике у Скупштину Аутономне покрајине Војводине") == \
        {"k": "stations", "e": "provincial", "d": None}
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
    assert store["docs"] == {"https://p.rs/a.pdf": {"m": "80314", "k": "minutes", "e": None, "d": None}}
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
    assert aside == [{"n": 8, "why": "lists add up to 648, valid votes read 654"}]  # never guessed


def test_list_names_from_proclamations():
    m = local.LIST_NAME.search("РЕШЕЊЕ о проглашењу изборне листе „ПРИМЕР – ЗА ГРАД“ коју је поднела")
    assert m.group(1) == "ПРИМЕР – ЗА ГРАД"
