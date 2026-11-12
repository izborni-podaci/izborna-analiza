"""RIK client against canned responses (the real service isn't reachable from tests)."""

import io
import json
import urllib.parse

import pytest

from izbori.rik import Client, RikError, guess_kind


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, headers: dict | None = None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_opener(routes: dict):
    calls = []

    def opener(req, timeout=None):
        form = urllib.parse.parse_qs((req.data or b"").decode())
        calls.append((req.full_url, form, dict(req.header_items())))
        for path, handler in routes.items():
            if req.full_url.endswith(path):
                return handler(form)
        raise AssertionError(f"unexpected request {req.full_url}")
    opener.calls = calls
    return opener


def test_rounds_summary_and_export():
    elections = {
        "1": {"rounds": {"700001": "Избори за председника Републике 2026."}},
        "2": {"rounds": {"680072": "Избори за народне посланике 2026."}},
    }
    summary = {
        "stat_sum_numbers": {"allowed_download": 1, "available": 1, "number_of_stations": "8392",
                             "processed_stations": "120", "datetime": "20.12.2026 21:10:00",
                             "election_title": "Избори за председника Републике", "total_voters": "6451292"},
        "table_data": [{"count_number": "2", "list_name": "2. ДРУГИ КАНДИДАТ"},
                       {"count_number": "1", "list_name": "1. ПРВИ КАНДИДАТ"}],
    }
    routes = {
        "/get-elections/": lambda form: FakeResponse(json.dumps(elections.get(form["election_type"][0], [])).encode()),
        "/get_results/": lambda form: FakeResponse(json.dumps(summary).encode()),
        "/export-results/700001/2": lambda form: FakeResponse(
            b"\xef\xbb\xbfbm_uid,bm_broj\n", {"Content-Disposition": 'attachment; filename="21:10:00_20.12.2026.csv"'}),
    }
    opener = make_opener(routes)
    c = Client(base="https://rik.test", opener=opener, sleep=lambda s: None)
    rounds = c.all_rounds()
    assert rounds["700001"]["kind"] == "presidential"
    assert rounds["680072"]["kind"] == "parliamentary"
    s = c.summary(1, "700001")
    assert (s.counted, s.total, s.allowed, s.counting) == (120, 8392, True, True)
    assert s.contestants == [(1, "ПРВИ КАНДИДАТ"), (2, "ДРУГИ КАНДИДАТ")]
    body, name = c.export("700001")
    assert name == "21:10:00_20.12.2026.csv"
    ua = [h for _, _, h in opener.calls if "User-agent" in h]
    assert ua and "javni-uvid/izborna-analiza" in ua[0]["User-agent"]


def test_export_that_is_not_csv_fails():
    opener = make_opener({"/export-results/1/2": lambda form: FakeResponse(b"<html>error</html>")})
    with pytest.raises(RikError):
        Client(base="https://rik.test", opener=opener, sleep=lambda s: None).export("1")


def test_guess_kind():
    assert guess_kind(9, "Избори за одборнике Скупштине града Београда") == "local"
    assert guess_kind(7, "Избори за посланике у Скупштину АП Војводине") == "provincial"
    assert guess_kind(5, "") == "unknown"
    # the short names RIK actually uses
    assert guess_kind(1, "Председнички 2026") == "presidential"
    assert guess_kind(9, "Локални 2024 - Београд") == "local"
    assert guess_kind(9, "Парламентарни 2026") == "parliamentary"
    assert guess_kind(9, "Покрајински 2023") == "provincial"


def test_register_page_and_counts():
    from izbori import documents

    def register(form):
        t = (form.get("filters[election_document_type]") or ["0"])[0]
        page = int(form["page"][0])
        assert form["data[election_round]"] == ["680072"] and form["election_type"] == ["2"]
        pages = {"29": 21, "12": 1}.get(t, 1)
        n = 10 if page < pages else {"29": 8, "12": 3}.get(t, 0)
        pagination = "".join(f'<a data-page="{p}">{p}</a>' for p in range(2, pages + 1))
        return FakeResponse(json.dumps({"records": [{}] * n, "pagination": pagination}).encode())

    opener = make_opener({"/get-election": register})
    client = Client(base="https://rik.test", opener=opener, sleep=lambda s: None)
    got = documents.counts(client, "680072", 2, types=(29, 12, 9))
    assert got == {"29": 208, "12": 3, "9": 0}
    assert len(opener.calls) == 4  # two requests for a kind with several pages, one otherwise
