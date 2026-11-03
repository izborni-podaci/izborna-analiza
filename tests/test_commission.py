"""The municipal electoral commissions' documents: kept by link, kind and day, never by title."""

import json

from izbori import commission
from izbori.boards import municipality_key


def record(n, municipality, decision_type, when="1793715861", name="ЗАПИСНИК СА 17. СЕДНИЦЕ"):
    return {"document_name": name, "municipality_display_name": municipality, "datetime": when,
            "decision_type": decision_type,
            "extfiles_link": [f'<div><a href="/extfile/sr/files/additionalDocuments/820/{n}/Записник {n}.pdf">'
                              "</a></div>"]}


CODES = {municipality_key("Трстеник"): "70254", municipality_key("Чукарица"): "70092"}


def test_records_keep_no_title_and_leave_out_riks_own():
    got = commission.parse_records([
        record(997, "Трстеник", "ИЗВЕШТАЈ", name="ЗБИРНИ ИЗВЕШТАЈ ... ОПШТИНЕ ТРСТЕНИК"),
        record(998, "Чукарица", "ЗАПИСНИЦИ СА СЕДНИЦА"),
        record(999, "РИК", "РЕШЕЊЕ", name="РЕШЕЊЕ О ПРОГЛАШЕЊУ ИЗБОРНЕ ЛИСТЕ"),
        record(1000, "Непозната", "ОДЛУКА")], CODES)
    assert [(i, d["m"], d["c"]) for i, d in got] == [("820997", "70254", "report"), ("820998", "70092", "session"),
                                                     ("8201000", "", "resolution")]
    assert all(set(d) == {"m", "c", "t", "u"} for _, d in got)  # no title is kept
    assert got[0][1]["u"] == "/extfile/sr/files/additionalDocuments/820/997/Записник 997.pdf"


def test_update_reads_everything_once_then_only_whats_new(tmp_path):
    pages = {1: [record(5, "Чукарица", "ЗАПИСНИЦИ СА СЕДНИЦА", "1793700000"),
                 record(4, "Чукарица", "ЗАПИСНИЦИ СА СЕДНИЦА", "1793700100")],
             2: [record(3, "Трстеник", "РЕШЕЊЕ", "1792000000")]}

    class Client:
        calls = []

        def get_json(self, path):
            page = int(path.split("page=")[1].split("&")[0])
            Client.calls.append(page)
            pagination = '<a data-page="1">1</a><a data-page="2">2</a>'
            return {"records": pages.get(page, []), "pagination": pagination}

    assert commission.update(Client(), tmp_path, "680072", 2, CODES, log=lambda m: None) == 3
    assert sorted(Client.calls) == [1, 2]
    Client.calls = []
    pages[1] = [record(6, "Чукарица", "ОДЛУКА", "1793800000"), *pages[1]]
    assert commission.update(Client(), tmp_path, "680072", 2, CODES, log=lambda m: None) == 1
    assert Client.calls == [1, 2]  # something new on the first page: the next one is read to be sure
    Client.calls = []
    assert commission.update(Client(), tmp_path, "680072", 2, CODES, log=lambda m: None) == 0
    assert Client.calls == [1]  # nothing new: one request
    store = json.loads((tmp_path / commission.FILE).read_text(encoding="utf-8"))
    assert store["complete"] and len(store["docs"]) == 4


def test_by_municipality_groups_by_kind_and_numbers_a_day_with_several():
    store = {"docs": {
        "a": {"m": "70092", "c": "session", "t": "1793700000", "u": "/x/a.pdf"},
        "b": {"m": "70092", "c": "session", "t": "1793700100", "u": "/x/b.pdf"},
        "c": {"m": "70092", "c": "session", "t": "1791000000", "u": "/x/c.pdf"},
        "d": {"m": "70092", "c": "decision", "t": "1792000000", "u": "/x/d.pdf"},
        "e": {"m": "", "c": "notice", "t": "1792000000", "u": "/x/e.pdf"}}}
    got = commission.by_municipality(store)
    assert list(got) == ["70092"]
    assert [g["kind"] for g in got["70092"]] == ["session", "decision"]
    assert [(d["day"], d["n"]) for d in got["70092"][0]["docs"]] == [("2026-10-03", 0), ("2026-11-03", 1),
                                                                     ("2026-11-03", 2)]
    assert got["70092"][0]["docs"][0]["url"] == "https://www.rik.parlament.gov.rs/x/c.pdf"
