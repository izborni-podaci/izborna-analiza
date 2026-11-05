"""The facts on the municipal commissions' page: what reached RIK's registers for each municipality, and when."""

from types import SimpleNamespace

from izbori import publishing
from izbori.documents import doc

MINUTES = "Записник о раду бирачког одбора (Образац РГ-2)"
REPEAT = "Записник о раду бирачког одбора са поновљеног гласања (Образац РГ-2)"
CORRECTION = "Решење о исправљању записника о раду бирачког одбора (Образац РГ-7-1)"


def _station(code, number, kind="domestic"):
    return SimpleNamespace(key=f"{code}/{number}", municipality_code=code, kind=kind)


def _mun(code, kind="domestic"):
    return {"code": code, "name": f"Општина {code}", "district": "Округ", "kind": kind}


def test_rows():
    a1, a2, a3, b1 = _station("1", "1"), _station("1", "2"), _station("1", "3"), _station("2", "1")
    abroad = _station("33000", "1", "abroad")
    docs = {
        a1.key: [doc(MINUTES, "/a1.pdf", "2026-10-25T22:00"), doc(CORRECTION, "/a1c.pdf", "2026-10-27T10:00")],
        a2.key: [doc(MINUTES, "/a2.pdf", "2026-10-26T00:30"), doc(MINUTES, "/a2b.pdf", "2026-10-25T23:00")],
        a3.key: [doc(REPEAT, "/a3.pdf", "2026-11-02T12:00")],  # only a repeat vote's minutes: not the station's own
        b1.key: [doc(MINUTES, "/b1.pdf", "2026-10-28T08:00")],
        abroad.key: [doc(MINUTES, "/x.pdf", "2026-10-26T08:00")],
    }
    boards = {a1.key: [SimpleNamespace(kind="board_standing"), SimpleNamespace(kind="board_extended")],
              a2.key: [SimpleNamespace(kind="board_standing")], b1.key: [SimpleNamespace(kind="board_standing")],
              a3.key: [SimpleNamespace(kind="board_standing"), SimpleNamespace(kind="board_extended")]}
    by_code = {"1": [a1, a2, a3], "2": [b1], "33000": [abroad]}
    close = publishing.closing("2026-10-25")
    rows = publishing.rows([_mun("1"), _mun("2"), _mun("33000", "abroad")], by_code, docs, close, boards,
                           {"1": 4}, {b1.key}, {"2": 3})
    assert [r.code for r in rows] == ["1", "2"]  # abroad is RIK's own
    a, b = rows
    assert (a.stations, a.minutes, a.corrections, a.late, a.changed) == (3, 2, 1, 0, 0)
    assert a.hours == 2.5  # the first minutes of each station: 2 h and 3 h after 20:00
    assert (a.standing, a.extended, a.cdocs) == (3, 2, 4)
    assert a.warn == {"minutes", "extended"}
    assert b.hours == 60 and b.late == 1 and (b.cdocs, b.city) == (0, 3) and b.changed == 1
    assert b.warn == {"hours", "late", "extended", "changed"}  # none from the commission: maybe filed under a city
    total = publishing.summary(rows, docs, [a1, a2, a3, b1, abroad], close, unplaced=7, city=3)
    assert (total["stations"], total["minutes"], total["late"], total["cdocs"], total["city"], total["unplaced"]) == (
        4, 3, 1, 4, 3, 7)
    assert total["hours"] == 3  # the median of every station in Serbia: 2, 3 and 60 hours

    # decisions or the commission's register not read: unknown, never zero
    rows = publishing.rows([_mun("1")], by_code, docs, close, None, None, set())
    assert rows[0].standing is None and rows[0].cdocs is None and not {"standing", "cdocs"} & rows[0].warn
    csv = publishing.to_csv(rows).splitlines()
    assert csv[0] == ",".join(publishing.COLUMNS)
    assert csv[1] == "1,Општина 1,Округ,3,2,2.5,0,1,,,,,0"


def test_minutes_timed_by_the_stamp_in_their_link():
    """The register of minutes sometimes gives a later time than the file's upload, which RIK stamps in the link
    (Bačka Palanka, 2023: the files came on election night, the register says two days later)."""
    url = "/extfile/sr/election_results/657fade37fe4c/@x.pdf"
    assert publishing.first_minutes([doc(MINUTES, url, "2023-12-20T11:39")]) == "2023-12-18T03:26"
    assert publishing.first_minutes([doc(MINUTES, "/no-stamp.pdf", "2023-12-20T11:39")]) == "2023-12-20T11:39"
    assert publishing.first_minutes([doc(REPEAT, url, "")]) == ""
