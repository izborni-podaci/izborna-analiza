"""Asking RIK less when no election is under way."""

import argparse
from datetime import UTC, datetime

from izbori import cli
from izbori.history import Archive


def archive_with(tmp_path, rounds: dict) -> Archive:
    a = Archive(tmp_path / "data")
    for rid, (date, counting) in rounds.items():
        a.save_meta(rid, {"kind": "parliamentary", "date": date})
        a.save_state(rid, {"signature": [1, 1], "counting": counting})
    a.save_known_rounds({rid: {"type": 2, "name": "", "kind": "parliamentary"} for rid in rounds})
    return a


def test_settled_rounds_and_quiet_hours(tmp_path):
    now = datetime(2027, 3, 3, 12, 17, tzinfo=UTC)  # a Wednesday
    a = archive_with(tmp_path, {"1": ("2026-10-25", False), "2": ("2027-02-20", False)})
    assert cli.settled(a, "1", now) and not cli.settled(a, "2", now)
    assert not cli.quiet_now(a, now)  # an election 11 days ago keeps the hourly look
    later = datetime(2027, 4, 7, 12, 17, tzinfo=UTC)
    assert cli.quiet_now(a, later)
    assert cli.look_now(datetime(2027, 4, 7, 10, 17, tzinfo=UTC))  # 12:17 in Belgrade (summer time), a quiet hour
    assert not cli.look_now(later)  # 14:17 in Belgrade
    assert cli.look_now(datetime(2027, 4, 11, 14, 17, tzinfo=UTC))  # Sunday: every hour
    a.save_state("1", {"signature": [1, 2], "counting": True})
    assert not cli.settled(a, "1", later)  # counting again, e.g. a repeat vote


def test_quiet_hour_asks_nothing_of_rik(tmp_path, monkeypatch):
    a = archive_with(tmp_path, {"1": ("2020-01-01", False)})

    class NoClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("RIK was asked")

    monkeypatch.setattr(cli, "Client", NoClient)
    monkeypatch.setattr(cli, "look_now", lambda now: False)
    args = argparse.Namespace(data=a.root, notes=tmp_path / "notes", always=False, commit=False, push=False,
                              watch=True, max_minutes=1, every=1, notify=False, dispatch_pages=False,
                              site_url="https://example.org/")
    assert cli.cmd_update(args) == 0
