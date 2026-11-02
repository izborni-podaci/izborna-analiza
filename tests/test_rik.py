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
    assert ua and "izborni-podaci" in ua[0]["User-agent"]


def test_export_that_is_not_csv_fails():
    opener = make_opener({"/export-results/1/2": lambda form: FakeResponse(b"<html>error</html>")})
    with pytest.raises(RikError):
        Client(base="https://rik.test", opener=opener, sleep=lambda s: None).export("1")


def test_guess_kind():
    assert guess_kind(9, "Избори за одборнике Скупштине града Београда") == "local"
    assert guess_kind(7, "Избори за посланике у Скупштину АП Војводине") == "provincial"
    assert guess_kind(5, "") == "unknown"
