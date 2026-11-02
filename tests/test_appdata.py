"""Rebuilding a round from RIK's results app. The station response mirrors RIK's real one (2023, Barajevo 1)."""

from izbori.appdata import minutes_field, rebuild
from izbori.boards import municipality_key
from izbori.load import parse

MINUTES_HTML = """
            <div class=''><span>Записник о раду бирачког одбора (Образац РГ-2)</span></div>
            <div class='table-file active'><a href='/extfile/sr/election_results/657f911ca973d/@ПА1_151c.pdf' target='_blank' rel='noopener noreferrer'>ПА1.pdf<span class='election-file active'></span></a><span>18-12-2023 01:23h</span></div>
            <div class=''><span>Записник о посматрачима (Образац РГ-11/НП)</span></div>
            <div class='table-file active'><a href='/extfile/sr/election_results/657f912b102d0/@ПА1-РГ11_73a5.pdf' target='_blank' rel='noopener noreferrer'>ПА1-РГ11.pdf<span class='election-file active'></span></a><span>18-12-2023 01:24h</span></div>"""

STATION = {
    "stat_sum_numbers": {"allowed_download": False, "available": "362", "datetime": "09.01.2024 20:21:00",
                         "election_title": "Парламентарни 2023", "number_of_stations": 1, "processed_stations": 1,
                         "total_voters": "624"},
    "table_data": [{"count_number": 1, "list_name": "1. ИЗБОРНА ЛИСТА А", "won_number": "176"},
                   {"count_number": 2, "list_name": "2. ИЗБОРНА ЛИСТА Б", "won_number": "23"},
                   {"count_number": 3, "list_name": "3. ИЗБОРНА ЛИСТА В", "won_number": "147"}],
    "sum_config": {"data": {"datasets": [{"data": [346, 16]}],
                            "labels": ["Важећи листићи (95.58%)", "Неважећи листићи (4.42%)"]}},
    "minute_from_election_station": MINUTES_HTML,
}


class FakeApp:
    base = "https://rik.test"

    def _json(self, path, form):
        assert path == "/get_results/"
        return {"stat_sum_numbers": {"election_title": "Парламентарни 2023", "number_of_stations": "1",
                                     "datetime": "09.01.2024 20:21:00"},
                "table_data": STATION["table_data"]}

    def regions(self, t, r):
        return {"1": "Београдски регион"}

    def municipalities(self, t, r, region):
        return [("1", "Градска општина Барајево")]

    def stations(self, t, r, region, mun):
        return {"159091": "1 - МК \"АРНАЈЕВО\""}

    def station_results(self, t, r, region, mun, st):
        return STATION


def test_minutes_field():
    links, entered = minutes_field(MINUTES_HTML)
    assert entered == "2023-12-18 01:23:00"
    assert links.count("|https://www.rik.parlament.gov.rs/extfile/") == 2


def test_rebuild_gives_rik_layout(round2026):
    codes = {municipality_key(s.municipality): s.municipality_code for s in round2026.stations}
    raw, info = rebuild(FakeApp(), 2, "341140", codes, threads=1, log=lambda m: None)
    stations, n = parse(raw)
    assert n == 3 and info["title"] == "Парламентарни 2023" and len(info["contestants"]) == 3
    [s] = stations
    assert s.key == "70092/1"  # same municipality code as in the 2026 file, so stations line up
    assert (s.registered, s.voted, s.valid, s.invalid, s.ballots) == (624, 362, 346, 16, 362)
    assert s.votes == [176, 23, 147]
    assert len(s.minutes_links) == 2 and s.district_code == "RS11"
    assert s.minutes_uploaded is not None
