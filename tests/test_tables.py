"""RIK's station tables for rounds before its results app. The rows mirror the 2022 presidential table."""

from izbori.load import parse
from izbori.tables import rik_time, table_rows

ROWS = [
    ["РЕЗУЛТАТИ ПО БИРАЧКИМ МЕСТИМА"], [],
    ["Округ", "Назив округа", "Општина", "Назив општине", "Рбр. бирачког места", "Уписани бирачи",
     "Изашли на изборе", "Број бирача који су гласали (Број гласачких листића у кутијама)", "Неважећи",
     "Важећи", "КАНДИДАТ А", "ДР КАНДИДАТ Б"],
    ["00", "Град Београд", 70092.0, "Барајево", 1.0, 645.0, 374.0, 372.0, 8.0, 364.0, 200.0, 164.0],
    ["99", "Заводи за извршење кривичних санкција", 55001.0, "Заводи", 3.0, 100.0, 90.0, 90.0, 0.0, 90.0, 50.0, 40.0],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
]


def test_table_gives_rik_layout():
    raw, info = table_rows(ROWS, {"70092": ("Београдски регион", "RS11")})
    stations, n = parse(raw)
    assert n == 2 and [c["name"] for c in info["contestants"]] == ["Кандидат А", "Др Кандидат Б"]
    s, prison = stations
    assert s.key == "70092/1" and s.district_code == "RS11"
    assert (s.registered, s.voted, s.ballots, s.invalid, s.valid) == (645, 374, 372, 8, 364)
    assert s.votes == [200, 164]
    assert prison.district_code == "/55001"


def test_rik_time_from_file_name():
    assert rik_time("/x/Tabela_3_po_birackim_mestima_predsednik_17_04_2022_01h16.XLS") == "17.04.2022 01:16:00"
    assert rik_time("/x/tabela.xls") is None
