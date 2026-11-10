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
        for folder, year, names in (
                ("SRB", "1999", ["Ada", "Dragash/Dragaš", "Mitrovica/Kosovska Mitrovica", "Peć/Peja", "Kamenica"]),
                ("XKX", "1999", ["Dragash/Dragaš", "Mitrovica/Kosovska Mitrovica", "Peć/Peja", "Kamenica",
                                 "Gjakova/Đakovica"]),
                ("XKX", "2001", ["Dragash/Dragaš", "Mitrovicë"])):
            shp, shx, dbf = layer(names)
            for ext, body in (("shp", shp), ("shx", shx), ("dbf", dbf), ("cpg", b"UTF-8")):
                z.writestr(f"ELWar_GESIS/{folder}_1992-2020/{year}.{ext}", body)
    wanted = {"90336": "Гора", "90298": "Косовска Митровица", "90239": "Пећ", "90140": "Косовска Каменица",
              "90263": "Приштина"}
    feats = geo.kim_features(archive.getvalue(), wanted, log=lambda m: None)
    # either of the two names, and Serbia's Gora as the municipality seated in Dragaš; Priština isn't in the layer
    assert [f["properties"]["code"] for f in feats] == ["90140", "90239", "90298", "90336", ""]
    # from Kosovo's own layer, the province's municipality without a station in RIK's results too, named in Serbian
    assert feats[-1]["properties"] == {"code": "", "name": "Ђаковица", "level": "", "source": "ELWar", "none": 1}
    assert all(f["properties"]["source"] == "ELWar" for f in feats)
    out = tmp_path / "municipalities.json"
    geo.write(out, feats, source="kept")
    back = json.loads(out.read_text(encoding="utf-8"))
    assert "Glaurdić" in back["attribution"] and "CC BY 4.0" in back["license"] and back["source"] == "kept"


def test_settlements_join_municipality_and_census(tmp_path):
    # one municipality, two settlements inside it (one with a census name, one with a name the census spells
    # differently and so unmatched), one outside every municipality
    muns = [{"type": "Feature", "properties": {"code": "79000"},  # a city around the municipality: the smaller wins
             "geometry": {"type": "Polygon", "coordinates": [[[21.6, 43.0], [22.0, 43.0], [22.0, 43.4], [21.6, 43.4],
                                                              [21.6, 43.0]]]}},
            {"type": "Feature", "properties": {"code": "70513"},
             "geometry": {"type": "Polygon", "coordinates": [[[21.7, 43.1], [21.9, 43.1], [21.9, 43.3], [21.7, 43.3],
                                                              [21.7, 43.1]]]}}]

    def square(x, y, d=0.03):
        return [pt(x, y), pt(x + d, y), pt(x + d, y + d), pt(x, y + d), pt(x, y)]
    data = {"elements": [
        {"type": "relation", "tags": {"ref:RS:naselje": "703966", "name": "Пуковац", "admin_level": "9"},
         "members": [{"type": "way", "role": "outer", "geometry": square(21.75, 43.15)}]},
        {"type": "relation", "tags": {"ref:RS:naselje": "703974", "name": "Русна (стари назив)", "admin_level": "9"},
         "members": [{"type": "way", "role": "outer", "geometry": square(21.8, 43.2)}]},
        {"type": "relation", "tags": {"ref:RS:naselje": "999999", "name": "Негде", "admin_level": "9"},
         "members": [{"type": "way", "role": "outer", "geometry": square(20.0, 44.0)}]},
        {"type": "relation", "tags": {"name": "no code"}, "members": []},
    ]}
    census = {"70513": {"PUKOVAC": "Пуковац", "RUSNA": "Русна"}}
    log = []
    feats = geo.settlement_features(data, muns, lambda code: census.get(code, {}), log=log.append)
    assert [(f["properties"]["code"], f["properties"]["municipality"], f["properties"]["census"]) for f in feats] == [
        ("703966", "70513", "Пуковац"), ("703974", "70513", "")]
    assert log == ["settlements: 2 boundaries, 1 without a census match, 1 outside every municipality"]
    out = tmp_path / "geo" / "settlements.json"
    geo.write_settlements(out, feats, "2026-11-08")
    grouped = geo.settlements_by_municipality(out)
    assert list(grouped) == ["70513"] and len(grouped["70513"]) == 2
    assert geo.settlements_by_municipality(tmp_path / "nowhere.json") == {}


def test_quarters_take_the_first_drawn_and_place_buildings():
    def rel(name, tags, ring):
        return {"type": "relation", "tags": dict(name=name, **tags),
                "members": [{"type": "way", "role": "outer", "geometry": [{"lon": x, "lat": y} for x, y in ring]}]}

    def sq(x0, y0, x1, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    els = [rel("Нови Сад", {"admin_level": "9", "boundary": "administrative"}, sq(0, 0, 10, 10)),
           rel("Телеп", {"place": "quarter"}, sq(0, 0, 5, 5)),
           rel("Лиман", {"place": "suburb"}, sq(5, 0, 10, 5)),
           rel("Лиман 1", {"place": "quarter"}, sq(5, 0, 8, 5)),
           rel("Шира", {"place": "suburb"}, sq(0, 4, 6, 10)),
           rel("Братство-Телеп", {"admin_level": "10", "boundary": "administrative"}, sq(1, 1, 2, 2)),
           rel("Сајлово", {"place": "neighbourhood"}, sq(1, 0.5, 4, 4.5)),  # inside Telep: a name, not a shape
           {"type": "node", "lon": 6, "lat": 1, "tags": {"name": "Основна школа „Вељко Петровић“", "amenity": "school"}},
           {"type": "node", "lon": 9, "lat": 9, "tags": {"name": "Нигде", "amenity": "school"}},
           {"type": "node", "lon": 2, "lat": 3, "tags": {"name": "Шангај", "place": "neighbourhood"}},
           {"type": "node", "lon": 7, "lat": 2, "tags": {"name": "Лиман", "place": "suburb"}}]
    feats, points = geo.quarter_features({"elements": els}, "Нови Сад", log=lambda *_: None)
    assert [f["properties"]["name"] for f in feats] == ["Лиман 1", "Телеп", "Шира"]  # smaller first; Liman is mostly Liman 1
    assert points == [["Основна школа „Вељко Петровић“", "Лиман 1"], ["Сајлово", "Телеп"], ["Шангај", "Телеп"],
                      ["месна заједница Братство-Телеп", "Телеп"]]  # Liman, over Liman 1 and more, is no name
