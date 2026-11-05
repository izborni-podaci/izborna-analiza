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


def test_kosovo_in_rik_s_division_by_name(tmp_path):
    """Kosovo and Metohija's municipalities come from a dataset of the municipalities of Yugoslavia's successor
    states, by year: the layer of the last year before they were redrawn, joined to RIK's codes by name."""
    import io
    import zipfile

    shapefile = pytest.importorskip("shapefile")

    def layer(names):
        shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
        w.field("CODE", "C")
        w.field("MUNICIPALI", "C")
        for k, name in enumerate(names):
            x = 20 + k * 0.2
            w.poly([[[x, 42], [x, 42.1], [x + 0.1, 42.1], [x + 0.1, 42], [x, 42]]])
            w.record(f"KOS_{k:03}", name)
        w.close()
        return shp.getvalue(), shx.getvalue(), dbf.getvalue()

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        for year, names in (("1999", ["Dragash/Dragaš", "Mitrovica/Kosovska Mitrovica", "Peć/Peja", "Kamenica"]),
                            ("2001", ["Dragash/Dragaš", "Mitrovicë"])):
            shp, shx, dbf = layer(names)
            for ext, body in (("shp", shp), ("shx", shx), ("dbf", dbf), ("cpg", b"UTF-8")):
                z.writestr(f"ELWar_GESIS/KOS_1992-2020/{year}.{ext}", body)
    wanted = {"90336": "Гора", "90298": "Косовска Митровица", "90239": "Пећ", "90140": "Косовска Каменица",
              "90263": "Приштина"}
    feats = geo.kim_features(archive.getvalue(), wanted, log=lambda m: None)
    # either of the two names, and Serbia's Gora as the municipality seated in Dragaš; Priština isn't in the layer
    assert [f["properties"]["code"] for f in feats] == ["90140", "90239", "90298", "90336"]
    assert all(f["properties"]["source"] == "ELWar" for f in feats)
    out = tmp_path / "municipalities.json"
    geo.write(out, feats, source="kept")
    back = json.loads(out.read_text(encoding="utf-8"))
    assert "Glaurdić" in back["attribution"] and "CC BY 4.0" in back["license"] and back["source"] == "kept"
