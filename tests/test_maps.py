"""A municipality's map by settlement: projection, colours by rank, the close-win shade, the legend."""
from izbori import maps


def square(x, y, d=0.1):
    return {"type": "Polygon", "coordinates": [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]]}


def test_settlement_map_colours_by_rank():
    feats = [{"type": "Feature", "properties": {"code": "1", "name": "Село", "census": "Село"}, "geometry": square(21, 43)},
             {"type": "Feature", "properties": {"code": "2", "name": "Град", "census": "Град"}, "geometry": square(21.1, 43)},
             {"type": "Feature", "properties": {"code": "3", "name": "Непознато", "census": ""}, "geometry": square(21.2, 43)}]
    results = {"Село": {"leader": 0, "share": 0.9, "second": 0.1}, "Град": {"leader": 2, "share": 0.4, "second": 0.38}}
    ranks = {0: 2, 1: 1, 2: 3}  # list 1 has most votes in the country, then 0, then 2
    labels = {0: "A", 1: "B", 2: "C"}
    svg, key = maps.settlement_map(feats, results, ranks, labels, "Тест", lambda x: f"{100 * x:.1f}%")
    assert key == []  # every square is wide enough for its name
    assert svg.startswith('<svg class="smap" viewBox="0 0 640 ') and svg.count("<path") == 3
    assert 'class="mp mp-2" d="M' in svg and "<title>Село · A 90.0%</title>" in svg
    assert 'class="mp mp-3 mp-close"' in svg and "Град · C 40.0%" in svg  # two points ahead: a lighter fill
    assert 'class="mp mp-none"' in svg and "<title>Непознато</title>" in svg
    # the drawing keeps the shape: three squares in a row at 43° N are about 2.2 times as wide as tall
    height = int(svg.split('viewBox="0 0 640 ')[1].split('"')[0])
    assert 280 < height < 310
    assert maps.legend(results, ranks, labels) == [{"cls": "mp-2", "label": "A", "n": 1}, {"cls": "mp-3", "label": "C", "n": 1}]
    assert maps.settlement_map([], results, ranks, labels, "x", str) == ("", [])


def test_names_fit_or_become_numbers():
    key = []
    assert maps.name_label("Село", (100, 50, 60), key) == '<text x="100.0" y="50.0">Село</text>'
    two = maps.name_label("Сремска Каменица", (100, 50, 70), key)
    assert two.count("<text") == 2 and ">Сремска<" in two and ">Каменица<" in two  # two lines, 11 px
    assert 'class="small"' in maps.name_label("Степановићево", (100, 50, 60), key)  # one long word: smaller
    assert maps.name_label("Лединци", (100, 50, 12), key) == '<text x="100.0" y="50.0" class="num">1</text>'
    assert key == ["Лединци"]
