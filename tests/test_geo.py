"""Municipal boundaries from OpenStreetMap: relations become one area per code."""

import json

import pytest

from izbori import geo

pytest.importorskip("shapely")  # only `izbori geo` needs it; the workflow adds it with `uv run --with shapely`


def pt(x, y):
    return {"lon": x, "lat": y}


def test_relations_become_areas_by_code(tmp_path):
    data = {"elements": [
        # a square drawn as two outer ways, with a hole
        {"type": "relation", "tags": {"ref:RS:opstina": "80012", "name": "Ада", "admin_level": "8"}, "members": [
            {"type": "way", "role": "outer", "geometry": [pt(20, 45), pt(20.1, 45), pt(20.1, 45.1)]},
            {"type": "way", "role": "outer", "geometry": [pt(20.1, 45.1), pt(20, 45.1), pt(20, 45)]},
            {"type": "way", "role": "inner",
             "geometry": [pt(20.04, 45.04), pt(20.06, 45.04), pt(20.06, 45.06), pt(20.04, 45.06), pt(20.04, 45.04)]}]},
        # a city with the same code: the municipality's own boundary wins
        {"type": "relation", "tags": {"ref:RS:grad": "80012", "admin_level": "7"}, "members": [
            {"type": "way", "role": "outer", "geometry": [pt(19, 44), pt(19.1, 44), pt(19.1, 44.1), pt(19, 44)]}]},
        # outer ways that don't close: no area
        {"type": "relation", "tags": {"ref:RS:opstina": "70017"}, "members": [
            {"type": "way", "role": "outer", "geometry": [pt(21, 43), pt(21.1, 43)]}]},
        # a city that has no municipality of its own
        {"type": "relation", "tags": {"ref:RS:grad": "71242", "name": "Чачак", "admin_level": "7"}, "members": [
            {"type": "way", "role": "outer",
             "geometry": [pt(20.3, 43.8), pt(20.5, 43.8), pt(20.5, 44.0), pt(20.3, 44.0), pt(20.3, 43.8)]}]},
    ]}
    feats = geo.features(data)
    assert [f["properties"]["code"] for f in feats] == ["71242", "80012"]
    ada = feats[1]
    assert ada["properties"]["name"] == "Ада" and len(ada["geometry"]["coordinates"]) == 2  # outer ring and hole
    out = tmp_path / "geo" / "municipalities.json"
    geo.write(out, feats, "2026-11-05")
    back = json.loads(out.read_text(encoding="utf-8"))
    assert back["attribution"] == "© OpenStreetMap contributors" and "ODbL" in back["license"]
    assert [f["properties"]["code"] for f in back["features"]] == ["71242", "80012"]
    assert out.read_text(encoding="utf-8").count("\n") == len(feats) + 2  # one feature per line
