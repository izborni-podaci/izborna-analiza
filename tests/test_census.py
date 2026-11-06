"""The 2022 census tables: downloaded as published, written only when they change, a failure stops nothing else."""

import hashlib
import json

from izbori import census, cli

XLSX = b"PK\x03\x04" + b"workbook"
XLS = b"\xd0\xcf\x11\xe0" + b"workbook"

TABLES = [
    census.Table("1/a-naselja.xlsx", "settlements", "Total population, by settlement"),
    census.Table("2/b.xls", "municipalities", "Population by ethnicity and sex"),
]


def opener(bodies):
    def get(url):
        body = bodies[url]
        if isinstance(body, Exception):
            raise body
        return body
    return get


def test_tables_are_kept_as_published_with_their_sources(tmp_path):
    bodies = {TABLES[0].url: XLSX, TABLES[1].url: XLS}
    changed, failed = census.fetch(tmp_path, TABLES, opener(bodies), log=lambda m: None, pause=0,
                                   now="2026-11-06T12:00:00Z")
    assert changed == ["settlements/a-naselja.xlsx", "municipalities/b.xls"] and failed == []
    assert (tmp_path / "settlements" / "a-naselja.xlsx").read_bytes() == XLSX
    assert (tmp_path / "municipalities" / "b.xls").read_bytes() == XLS
    text = (tmp_path / "sources.json").read_text(encoding="utf-8")
    sources = json.loads(text)
    entry = sources["tables"]["settlements/a-naselja.xlsx"]
    assert entry == {"url": census.BASE + "1/a-naselja.xlsx", "title": "Total population, by settlement",
                     "sha256": hashlib.sha256(XLSX).hexdigest(), "bytes": len(XLSX),
                     "fetched": "2026-11-06T12:00:00Z"}
    assert sources["source"] == census.SOURCE
    assert text.count("\n") == len(TABLES) + 2  # one table per line


def test_an_unchanged_table_is_left_alone(tmp_path):
    bodies = {TABLES[0].url: XLSX, TABLES[1].url: XLS}
    census.fetch(tmp_path, TABLES, opener(bodies), log=lambda m: None, pause=0, now="2026-11-06T12:00:00Z")
    before = (tmp_path / "sources.json").read_text(encoding="utf-8")
    changed, failed = census.fetch(tmp_path, TABLES, opener(bodies), log=lambda m: None, pause=0,
                                   now="2026-11-07T12:00:00Z")
    assert changed == [] and failed == []
    assert (tmp_path / "sources.json").read_text(encoding="utf-8") == before  # the first fetch time stays

    bodies[TABLES[1].url] = XLS + b" corrected"
    changed, _ = census.fetch(tmp_path, TABLES, opener(bodies), log=lambda m: None, pause=0,
                              now="2026-11-08T12:00:00Z")
    assert changed == ["municipalities/b.xls"]
    sources = json.loads((tmp_path / "sources.json").read_text(encoding="utf-8"))
    assert sources["tables"]["municipalities/b.xls"]["fetched"] == "2026-11-08T12:00:00Z"
    assert sources["tables"]["settlements/a-naselja.xlsx"]["fetched"] == "2026-11-06T12:00:00Z"


def test_a_failure_or_an_error_page_stops_nothing_else(tmp_path):
    bodies = {TABLES[0].url: b"<!DOCTYPE html><title>Not found</title>", TABLES[1].url: XLS}
    changed, failed = census.fetch(tmp_path, TABLES, opener(bodies), log=lambda m: None, pause=0)
    assert changed == ["municipalities/b.xls"] and failed == ["settlements/a-naselja.xlsx"]
    assert not (tmp_path / "settlements").exists()
    assert list(json.loads((tmp_path / "sources.json").read_text(encoding="utf-8"))["tables"]) == \
        ["municipalities/b.xls"]

    bodies = {TABLES[0].url: OSError("connection reset"), TABLES[1].url: OSError("timed out")}
    changed, failed = census.fetch(tmp_path / "none", TABLES, opener(bodies), log=lambda m: None, pause=0)
    assert changed == [] and len(failed) == 2
    assert not (tmp_path / "none").exists()  # nothing to record, no file


def test_the_tables_listed():
    keys = [t.key for t in census.TABLES]
    assert len(keys) == len(set(keys)) and len({t.url for t in census.TABLES}) == len(keys)
    assert {t.level for t in census.TABLES} == {"settlements", "municipalities"}
    assert all(t.url.startswith("https://popis2022.stat.gov.rs/media/") for t in census.TABLES)


def test_command_fails_when_a_table_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(census, "TABLES", TABLES)
    monkeypatch.setattr(census, "PAUSE", 0)
    bodies = {TABLES[0].url: XLSX, TABLES[1].url: OSError("timed out")}
    monkeypatch.setattr(census, "get", opener(bodies))
    out = tmp_path / "census"
    assert cli.main(["--data", str(tmp_path), "census", "--out", str(out)]) == 1
    assert (out / "settlements" / "a-naselja.xlsx").exists()
    bodies[TABLES[1].url] = XLS
    assert cli.main(["--data", str(tmp_path), "census", "--out", str(out)]) == 0
