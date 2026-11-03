"""Documents RIK publishes per polling station: the register of minutes, and how they show up."""

import json

from izbori import documents
from izbori.checks import document_flags
from izbori.documents import classify, doc, for_station, form, parse_record, uploaded_at

RG2 = "Записник о раду бирачког одбора (Образац РГ-2)"
RG11 = "Записник о посматрачима (Образац РГ-11/НП)"


def entry(label: str, href: str, when: str) -> str:
    return (f"\n<div class=''><span>{label}</span></div>\n<div class='table-file active'><a href='{href}' "
            f"target='_blank' rel='noopener noreferrer'>x.pdf<span class='election-file active'></span></a>"
            f"<span>{when}</span></div>")


def record(municipality: str, number: str, *entries: str) -> dict:
    return {"municipality": municipality, "election_station_number": number, "election_station_name": "ОШ",
            "number": "1.", "extfiles": [{"date": "", "extfile": "".join(entries), "uid": "x"}]}


def test_kinds_of_documents():
    assert classify(RG2) == ("minutes", False)
    assert classify("Записник о раду бирачког одбора са поновљеног гласања (Образац РГ-2) - II") == ("minutes", True)
    assert classify(RG11) == ("observers", False)
    assert classify("Примедба - поновно гласање I") == ("remark", True)
    assert classify("Решење о поништавању гласања на бирачком месту (Образац РГ-9)") == ("annulled", False)
    assert classify("Решење којим се констатује да се на бирачком месту не могу утврдити резултати гласања "
                    "(Образац РГ-8)") == ("undetermined", False)
    assert classify("Извештај о контроли записника о раду бирачког одбора по узорку (Образац РГ-6)")[0] == "audit"
    assert classify("Исправка решења")[0] == "correction"
    assert form("Решење о исправљању записника о раду бирачког одбора (Образац РГ-7-2)") == "RG-7-2"
    assert form(RG2) == "" and form(RG11) == ""


def test_upload_time_from_the_link():
    assert uploaded_at("/extfile/sr/election_results/799/001/6ade74fca1e84/@БМ 1 - РГ-2_ccb6.pdf") == "2026-10-25T22:30"
    assert uploaded_at("https://example.org/no-stamp.pdf") == ""


def test_register_record_and_store(tmp_path):
    rec = record("Град Нови Сад", "5",
                 entry(RG2, "/extfile/sr/election_results/799/001/6ade74fca1e84/@БМ 5 - РГ-2_a.pdf", "25-10-2026 22:30h"),
                 entry(RG11, "/extfile/sr/election_results/799/052/6ade751ba7cbb/@БМ 5 - РГ-11_b.pdf", "25-10-2026 22:31h"),
                 entry("Примедба", "/extfile/sr/election_results/801/371/6ade7b1be1216/@Primedba 5_c.pdf",
                       "25-10-2026 22:56h"))
    municipality, number, docs = parse_record(rec)
    assert (municipality, number) == ("Град Нови Сад", "5")
    assert [d.kind for d in docs] == ["minutes", "observers", "remark"]
    assert docs[1].url.startswith("https://www.rik.parlament.gov.rs/extfile/") and docs[2].uploaded == "2026-10-25T22:56"
    data = documents.store([parse_record(rec), parse_record(record("Непозната", "1", entry(RG2, "/a.pdf", "25-10-2026 22:30h")))],
                           {"NOVISAD": "89010"})
    assert list(data["stations"]) == ["89010/5"] and data["unmatched"] == [["Непозната", "1"]]
    assert "Gradska" not in json.dumps(data) and len(data["labels"]) == 3
    assert documents.save(tmp_path, data) and not documents.save(tmp_path, data)  # unchanged: not written again
    loaded = documents.load(tmp_path)["89010/5"]
    assert [(d.kind, d.uploaded) for d in loaded] == [(d.kind, d.uploaded) for d in docs]


def test_a_station_lists_each_document_once():
    csv_links = [(RG2, "https://rik.parlament.gov.rs/extfile/sr/election_results/799/001/6ade74fca1e84/@БМ 1 - РГ-2_a.pdf")]
    register = [doc(RG2, "/extfile/sr/election_results/799/001/6ade74fca1e84/%40%D0%91%D0%9C%201%20-%20%D0%A0%D0%93-2_a.pdf"),
                doc(RG11, "/extfile/sr/election_results/799/052/6ade751ba7cbb/@БМ 1 - РГ-11_b.pdf")]
    docs = for_station(csv_links, register)
    assert [d.kind for d in docs] == ["minutes", "observers"]


def test_flags_say_a_document_exists():
    docs = {"1/1": [doc("Примедба", "/a/6ade7b1be1216/@p.pdf"), doc("Примедба", "/b/6ade7b1be1217/@q.pdf")],
            "1/2": [doc("Решење о поништавању гласања на бирачком месту (Образац РГ-9)", "/c/6ae263fd367dc/@r.pdf")],
            "1/3": [doc(RG11, "/d/6ade751ba7cbb/@s.pdf")]}
    flags = {(f.station, f.code): f.data for f in document_flags(docs)}
    assert set(flags) == {("1/1", "remark_filed"), ("1/2", "voting_annulled")}  # an observers' record alone is no flag
    assert flags[("1/1", "remark_filed")]["n"] == 2 and flags[("1/2", "voting_annulled")]["forms"] == ["RG-9"]


def test_archived_rounds_carry_their_documents(archive):
    from izbori.report import analyze
    a = analyze(archive, "341140")
    kinds = {d.kind for docs in a.documents.values() for d in docs}
    assert {"minutes", "observers", "correction", "annulled", "undetermined"} <= kinds
    assert sum(1 for f in a.flags if f.code == "voting_annulled") == 13
    s = next(s for s in a.round.stations if any(d.kind == "observers" for d in a.documents.get(s.key, [])))
    assert classify(next(lbl for lbl, url in s.minutes_links if url == s.minutes_url))[0] == "minutes"
