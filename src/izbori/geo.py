"""Municipal boundaries for the map on the Compare page, from OpenStreetMap.

OpenStreetMap's Serbian boundaries came from the cadastre's open register of spatial units, and they carry its
municipality and city codes (`ref:RS:opstina`, `ref:RS:grad`): the same matični broj RIK uses, so each boundary
joins RIK's municipalities by code. `izbori geo` fetches them once, on a GitHub runner, through the Overpass API,
simplifies them to what a map of the whole country needs and writes data/geo/municipalities.json. The file is a
database derived from OpenStreetMap, so it is under the ODbL and every map built from it names its source.

Shapely assembles and simplifies the polygons. It is needed only by this command, not to build the site, so it isn't
a dependency of the package: the workflow runs `uv run --with shapely izbori geo`."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
QUERY = """[out:json][timeout:900];
(
  relation["boundary"="administrative"]["ref:RS:opstina"];
  relation["boundary"="administrative"]["ref:RS:grad"];
);
out geom;"""
AGENT = "izborna-analiza (https://github.com/izborni-podaci/izborna-analiza)"
ATTRIBUTION = "© OpenStreetMap contributors"
LICENSE = "ODbL 1.0, https://opendatacommons.org/licenses/odbl/1-0/ (data: https://www.openstreetmap.org/copyright)"
TOLERANCE = 0.003  # degrees, about 250 m: a pixel or less on a map of the whole country
DIGITS = 4  # about 10 m


def fetch(query: str = QUERY, timeout: int = 960) -> dict:
    """The relations with their member ways' geometry, from the first Overpass server that answers."""
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt, url in enumerate(OVERPASS * 2):
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - a busy server: try the next one
            last = e
            time.sleep(30 * (attempt + 1))
    raise RuntimeError(f"Overpass didn't answer: {last}")


def geometry(relation: dict):
    """A relation's area: the outer ways joined into rings, less the inner ones. None when the outer ways don't
    close."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    lines: dict[str, list] = {"outer": [], "inner": []}
    for m in relation.get("members", []):
        pts = [(p["lon"], p["lat"]) for p in m.get("geometry") or [] if p]
        if m.get("type") != "way" or len(pts) < 2:
            continue
        lines["inner" if m.get("role") == "inner" else "outer"].append(LineString(pts))
    if not lines["outer"]:
        return None

    def faces(ways):
        noded = unary_union(ways)  # joined and split where they meet, as polygonize needs
        return unary_union(list(polygonize(getattr(noded, "geoms", [noded]))))

    area = faces(lines["outer"])
    if lines["inner"]:
        area = area.difference(faces(lines["inner"]))
    return None if area.is_empty else area


def _round(coords):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], DIGITS), round(coords[1], DIGITS)]
    return [_round(c) for c in coords]


def features(data: dict) -> list[dict]:
    """One feature per code: a municipality's own boundary where it has one, otherwise the city's."""
    from shapely import set_precision
    from shapely.geometry import mapping

    best: dict[str, tuple[int, dict]] = {}
    for rel in data.get("elements", []):
        tags = rel.get("tags", {})
        code = (tags.get("ref:RS:opstina") or tags.get("ref:RS:grad") or "").strip()
        if not code.isdigit():
            continue
        rank = 0 if tags.get("ref:RS:opstina") else 1
        if code in best and best[code][0] <= rank:
            continue
        area = geometry(rel)
        if area is None:
            continue
        area = set_precision(area.simplify(TOLERANCE, preserve_topology=True), 10 ** -DIGITS)
        if area.is_empty:
            continue
        shape = mapping(area)
        best[code] = (rank, {"type": "Feature",
                             "properties": {"code": code, "name": tags.get("name", ""),
                                            "level": tags.get("admin_level", "")},
                             "geometry": {"type": shape["type"], "coordinates": _round(shape["coordinates"])}})
    return [best[code][1] for code in sorted(best)]


def write(path: Path, feats: list[dict], fetched: str) -> None:
    """The boundaries as GeoJSON, one feature per line so git keeps a small diff when a few change."""
    head = {"type": "FeatureCollection", "attribution": ATTRIBUTION, "license": LICENSE,
            "source": f"OpenStreetMap through the Overpass API, {fetched}"}
    lines = [json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in feats]
    text = json.dumps(head, ensure_ascii=False)[:-1] + ', "features": [\n' + ",\n".join(lines) + "\n]}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
