"""Asking RIK by the election calendar: often around an election, once a day otherwise."""

import argparse
from datetime import UTC, datetime, timedelta

from izbori import cli, schedule
from izbori.history import Archive


def archive_with(tmp_path, rounds: dict, listed: tuple = ()) -> Archive:
    a = Archive(tmp_path / "data")
    for rid, (date, counting) in rounds.items():
        a.save_meta(rid, {"kind": "parliamentary", "date": date})
        a.save_state(rid, {"signature": [1, 1], "counting": counting})
    a.save_known_rounds({rid: {"type": 2, "name": "", "kind": "parliamentary"} for rid in (*rounds, *listed)})
    return a


def test_settled_rounds(tmp_path):
    now = datetime(2027, 3, 3, 12, 17, tzinfo=UTC)
    a = archive_with(tmp_path, {"1": ("2026-10-25", False), "2": ("2027-02-20", False)})
    assert cli.settled(a, "1", now) and not cli.settled(a, "2", now)
    a.save_state("1", {"signature": [1, 2], "counting": True})
    assert not cli.settled(a, "1", now)  # counting again, e.g. a repeat vote


def test_how_often_by_the_calendar(tmp_path):
    a = archive_with(tmp_path, {"1": ("2026-10-25", False)})
    at = lambda *t: datetime(*t, tzinfo=UTC)  # noqa: E731
    assert schedule.every(a, at(2027, 3, 3, 12, 17))[0] == timedelta(days=1)  # nothing near: once a day
    assert schedule.every(a, at(2026, 10, 25, 8, 17))[0] == timedelta(hours=6)  # election day, polls open
    assert schedule.every(a, at(2026, 10, 25, 17, 17))[0] == timedelta(hours=1)  # 18:17 in Belgrade
    assert schedule.every(a, at(2026, 10, 27, 12, 17))[0] == timedelta(hours=1)  # two days after
    assert schedule.every(a, at(2026, 11, 3, 12, 17))[0] == timedelta(hours=3)  # nine days after
    assert schedule.every(a, at(2026, 11, 9, 12, 17))[0] == timedelta(days=1)  # fifteen days after
    a.save_state("1", {"signature": [1, 2], "counting": True})
    assert schedule.every(a, at(2026, 11, 1, 12, 17))[0] == timedelta(0)  # a count is open: every run
    assert schedule.every(a, at(2027, 3, 3, 12, 17))[0] == timedelta(days=1)  # one RIK left open months ago isn't
    # an election entered in the calendar before RIK has any results
    b = archive_with(tmp_path / "b", {"1": ("2026-10-25", False)}, listed=("2",))
    (b.root / schedule.ELECTIONS).write_text("date,round,kind,note\n2027-04-11,2,local,\n", encoding="utf-8")
    assert schedule.every(b, at(2027, 4, 11, 19, 0)) == (timedelta(hours=1), "the election of 2027-04-11")
    assert schedule.every(b, at(2027, 4, 4, 19, 0))[0] == timedelta(days=1)  # a Sunday, but its date is known
    # a round RIK lists without a known date: every hour on Sundays, in case it is that day
    (b.root / schedule.ELECTIONS).write_text("date,round,kind,note\n", encoding="utf-8")
    assert schedule.undated(b) == ["2"]
    assert schedule.every(b, at(2027, 4, 4, 19, 0))[0] == timedelta(hours=1)
    assert schedule.every(b, at(2027, 4, 7, 19, 0))[0] == timedelta(days=1)


def test_a_skipped_run_does_not_delay_the_next_look(tmp_path):
    a = archive_with(tmp_path, {"1": ("2020-01-01", False)})
    now = datetime(2027, 3, 3, 12, 17, tzinfo=UTC)
    assert schedule.due(a.root, "rik", now, timedelta(days=1))  # never asked
    schedule.record(a.root, now, "rik")
    assert not schedule.due(a.root, "rik", now + timedelta(hours=5), timedelta(days=1))
    assert schedule.due(a.root, "rik", now + timedelta(hours=23, minutes=45), timedelta(days=1))  # the run drifts
    assert schedule.due(a.root, "rik", now + timedelta(days=3), timedelta(days=1))


def test_no_look_due_asks_nothing_of_rik(tmp_path, monkeypatch):
    a = archive_with(tmp_path, {"1": ("2020-01-01", False)})
    schedule.record(a.root, datetime.now(UTC) - timedelta(hours=2), "rik")

    class NoClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("RIK was asked")

    monkeypatch.setattr(cli, "Client", NoClient)
    args = argparse.Namespace(data=a.root, notes=tmp_path / "notes", always=False, commit=False, push=False,
                              watch=True, max_minutes=1, every=1, notify=False, dispatch_pages=False, rerun=False,
                              site_url="https://example.org/")
    assert cli.cmd_update(args) == 0
