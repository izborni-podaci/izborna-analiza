import math

import pytest

from izbori import sheet


def test_readings_best_first_and_without_a_stray_mark():
    p = [[0.0] * 10 for _ in range(3)]
    p[0][3], p[0][8] = .9, .1
    p[1][1], p[1][7] = .6, .4
    p[2][1] = 1.0  # a stub read as 1
    got = sheet.readings(p)
    assert got[0][0] == 311
    values = [v for v, _ in got]
    assert 371 in values and 31 in values
    assert sheet.readings([]) == [(0, math.log(.5))]


def test_adds_up():
    assert sheet.adds_up([573, 316, 316, 11, 305, 257, 0, 43, 5], 4)
    assert not sheet.adds_up([573, 316, 316, 11, 305, 257, 0, 43, 6], 4)  # lists don't add up
    assert not sheet.adds_up([300, 316, 316, 11, 305, 257, 0, 43, 5], 4)  # more voters than registered
    assert not sheet.adds_up([573, 316, 316, 11, 305, 257, 0, None, 5], 4)
    assert not sheet.adds_up([573, 316, 316, 11, 305], 4)


def test_lists_from_the_tables_and_short_names():
    assert sheet.lists_count({"a": [0] * 10, "b": [0] * 10, "c": [0] * 7, "d": []}) == 4
    assert sheet.lists_count({"a": [0] * 3}) == 0
    names = sheet.short_names(["80373-biracko-mesto-1", "80373-biracko-mesto-12",
                               "80373-biracko-mesto-8-ponovljeno-glasanje", "80373-odluka"])
    assert names["80373-biracko-mesto-1"] == "1"
    assert names["80373-biracko-mesto-8-ponovljeno-glasanje"] == "8-ponovljeno-glas…"
    assert names["80373-odluka"] == "80373-odluka"


def test_crops_grouped_by_minutes(tmp_path):
    for n in ("80446-lo2-p1-2.png", "80446-lo2-p1-1.png", "80446-lo10-p2-2.png", "x.png"):
        (tmp_path / n).write_bytes(b"")
    got = sheet.station_crops(tmp_path)
    assert list(got) == ["80446-lo10", "80446-lo2"]
    assert [p.name for p in got["80446-lo2"]] == ["80446-lo2-p1-1.png", "80446-lo2-p1-2.png"]


def _form(values):
    """A drawn results table: a left column and a value column, one row per value (None: a heading row)."""
    import cv2
    import numpy as np
    h = 40 + 120 * len(values)
    img = np.full((h, 1600), 255, np.uint8)
    for x in (100, 1200, 1500):
        cv2.line(img, (x, 20), (x, h - 20), 0, 3)
    for i in range(len(values) + 1):
        cv2.line(img, (100, 20 + 120 * i), (1500, 20 + 120 * i), 0, 3)
    for i, v in enumerate(values):
        if v is not None:
            cv2.putText(img, str(v), (1260, 20 + 120 * i + 85), cv2.FONT_HERSHEY_SIMPLEX, 2.2, 0, 5)
    return img


def test_cells_found_by_the_ruled_lines():
    pytest.importorskip("cv2")
    cells = sheet.ruled_cells(_form([316, 316, 11, 305, None, None, 257, 0, 43, 5]))
    assert len(cells) == 10
    assert all(abs(c[2] - 1200) < 6 and abs(c[3] - 1500) < 6 for c in cells)


def test_sheets_from_crops(tmp_path):
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    crops, out = tmp_path / "crops", tmp_path / "out"
    crops.mkdir()
    for st in (1, 2):
        band = _form([573])
        cv2.imwrite(str(crops / f"80446-lo{st}-p1-1.png"), band)
        cv2.imwrite(str(crops / f"80446-lo{st}-p1-2.png"), _form([316, 316, 11, 305, None, None, 257, 0, 43, 5]))
    cv2.imwrite(str(crops / "80446-lo3-p1-2.png"), np.full((300, 1600), 255, np.uint8))  # no table: read whole
    got = sheet.make_sheets(crops, out, model=None, log=lambda *_: None)
    assert got["lists"] == 4 and got["rows"] == 2 and got["whole"] == ["lo3"]
    assert (out / "sheet-1.png").exists() and (out / "whole" / "80446-lo3-p1-2.png").exists()
    lines = (out / "guesses.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("minutes,upisani,izašli,kutija,nevažeći,važeći,lista 1")
    assert lines[1] == "lo1,,,,,,,,,,False"
