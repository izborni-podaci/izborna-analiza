"""Cities split into several municipalities: which they are, how they add up, how they are named."""
from types import SimpleNamespace as NS

from izbori import cities


def station(code, municipality, district="", counted=True, registered=100, voted=70, ballots=70, invalid=2):
    return NS(municipality_code=code, municipality=municipality, district=district, district_code="1/2", counted=counted,
              registered=registered, voted=voted, ballots=ballots, invalid=invalid)


def test_cities_from_the_results_names():
    sts = [station("70203", "Градска општина Палилула (Београд)", "Београдски регион/Град Београд"),
           station("70246", "Градска општина Стари Град", "Београдски регион/Град Београд"),
           station("71331", "Ниш-Медијана", "Регион Јужне и Источне Србије/Нишавски управни округ"),
           station("71307", "Ниш-Пантелеј", "Регион Јужне и Источне Србије/Нишавски управни округ"),
           station("70947", "Град Пожаревац"), station("71340", "Градска општина Костолац"), station("70017", "Општина Александровац")]
    parts = {"70203": ("name", "BEOGRAD"), "70246": ("name", "BEOGRAD"), "71331": ("name", "NIS"), "71307": ("name", "NIS"),
             "71340": ("code", "70947")}
    out = cities.cities(parts, sts)
    assert sorted(out) == ["beograd", "nis", "pozarevac"]
    assert out["beograd"].name == "Београд" and out["beograd"].codes == ["70203", "70246"] and out["beograd"].own is None
    assert out["nis"].name == "Ниш" and sorted(out["nis"].codes) == ["71307", "71331"]
    assert out["pozarevac"].name == "Пожаревац" and out["pozarevac"].codes == ["70947", "71340"] and out["pozarevac"].own == "70947"
    # Belgrade's groups: central before outer, by name inside; other cities have none
    b = out["beograd"]
    assert b.group_of("70246") == "central" and b.group_of("70092") == "outer" and out["nis"].group_of("71331") is None
    assert b.order("70092", "Барајево") > b.order("70254", "Чукарица")
    assert out["pozarevac"].order("70947", "Град Пожаревац") < out["pozarevac"].order("71340", "Костолац")


def test_add_up_and_names():
    rows = [{"stations": 2, "flagged": 1}, {"stations": 1, "flagged": 0}]
    sts = [station("a", "x", registered=100, voted=80, ballots=80, invalid=4), station("a", "x", counted=False),
           station("b", "y", registered=100, voted=60, ballots=60, invalid=0)]
    total = cities.add_up(rows, sts)
    assert total == {"stations": 3, "counted": 2, "registered": 200, "voted": 140, "turnout": 0.7, "invalid": 4 / 140,
                     "flagged": 1, "flagged_share": 1 / 3, "municipalities": 2}
    assert cities.short_name("Градска општина Палилула (Београд)") == "Палилула"
    assert cities.short_name("Град Пожаревац") == "Пожаревац" and cities.short_name("Костолац") == "Костолац"
    assert cities.slug_of("NIS") == "nis"
