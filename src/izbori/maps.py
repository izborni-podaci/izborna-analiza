"""A municipality's map by settlement, as SVG drawn when the site is built.

The settlements' boundaries come from data/geo/settlements.json (geo.py, OpenStreetMap). Each settlement is a path
coloured by the list that is first there: not by the list's identity but by its rank in the whole election, the
same palette the seats use (--s1 … --s8), so a reader learns the colours once per election. A close win (under
`CLOSE` points) is drawn lighter; a settlement without a result or without a census match is grey.
"""
from __future__ import annotations

import math
from html import escape

WIDTH = 640  # CSS pixels of the drawing's width; the height follows the municipality's shape, within MAX_HEIGHT
MAX_HEIGHT = 520
CLOSE = 0.05  # the leader fewer than this many points ahead: a lighter fill
PALETTE = 8  # lists ranked past this share the "other" colour


def _rings(geometry: dict):
    if geometry["type"] == "Polygon":
        yield from geometry["coordinates"]
    elif geometry["type"] == "MultiPolygon":
        for poly in geometry["coordinates"]:
            yield from poly


def project(features: list[dict], width: int = WIDTH, max_height: int = MAX_HEIGHT):
    """A function from (lon, lat) to drawing coordinates, and the drawing's height: an equirectangular projection
    scaled by the cosine of the middle latitude, fitted to the width."""
    xs, ys = [], []
    for f in features:
        for ring in _rings(f["geometry"]):
            for lon, lat in ring:
                xs.append(lon)
                ys.append(lat)
    if not xs:
        return None, 0
    lat0 = (min(ys) + max(ys)) / 2
    k = math.cos(math.radians(lat0))
    span_x = (max(xs) - min(xs)) * k or 1e-9
    span_y = (max(ys) - min(ys)) or 1e-9
    scale = min((width - 4) / span_x, (max_height - 4) / span_y)
    height = round(span_y * scale + 4)
    x0, y1 = min(xs), max(ys)

    def to(lon: float, lat: float) -> tuple[float, float]:
        return 2 + (lon - x0) * k * scale, 2 + (y1 - lat) * scale
    return to, height


LABEL_PX = 6.2  # about the width of a letter at the label's size (11 px), to tell whether a name fits
SMALL_PX = 5.0  # at the smaller size (9 px)
NUMBER_MIN = 22  # narrower than this, a settlement gets a number and its name goes in the key under the map


def label_point(geometry: dict, to):
    """Where a settlement's name goes: the centroid of its largest ring (by area), and that ring's width in
    pixels. The centroid can fall outside a crescent; good enough for the names that fit."""
    best, best_area = None, -1.0
    for ring in _rings(geometry):
        pts = [to(lon, lat) for lon, lat in ring]
        area = cx = cy = 0.0
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            cross = x1 * y2 - x2 * y1
            area += cross
            cx += (x1 + x2) * cross
            cy += (y1 + y2) * cross
        if abs(area) > best_area and area:
            best_area = abs(area)
            xs = [x for x, _ in pts]
            best = (cx / (3 * area), cy / (3 * area), max(xs) - min(xs))
    return best


def path_d(geometry: dict, to) -> str:
    parts = []
    for ring in _rings(geometry):
        pts = [to(lon, lat) for lon, lat in ring]
        parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
    return "".join(parts)


def settlement_map(features: list[dict], results: dict[str, dict], ranks: dict[int, int], labels: dict[int, str],
                   title: str, pct, width: int = WIDTH) -> str:
    """The SVG. results: census settlement name → {"leader": list index or None, "share", "second"} (from
    coordinator.by_settlement); ranks: list index → its rank in the election (1 = most votes); labels: list index →
    display label. Returns the SVG and the key (the names of the settlements too narrow for their name, in the
    order of their numbers); an empty string when there is nothing to draw."""
    to, height = project(features, width)
    if to is None:
        return "", []
    paths, texts, key = [], [], []
    for f in sorted(features, key=lambda f: f["properties"].get("census") or ""):
        p = f["properties"]
        r = results.get(p.get("census") or "")
        cls, tip = "mp-none", escape(p.get("census") or p.get("name") or "")
        label = p.get("census") or p.get("name") or ""
        spot = label_point(f["geometry"], to) if label else None
        if spot:
            texts.append(name_label(label, spot, key))
        if r and r.get("leader") is not None:
            rank = ranks.get(r["leader"], PALETTE + 1)
            cls = f"mp-{min(rank, PALETTE + 1)}"
            if r.get("second") is not None and r["share"] - r["second"] < CLOSE:
                cls += " mp-close"
            tip += f" · {escape(labels.get(r['leader'], ''))} {pct(r['share'])}"
        paths.append(f'<path class="mp {cls}" d="{path_d(f["geometry"], to)}" data-set="{escape(p.get("census") or "")}">'
                     f"<title>{tip}</title></path>")
    # a close win is hatched in the list's colour rather than painted lighter: two shades of one colour were
    # too alike, and stripes survive print and a dark page
    defs = "".join(f'<pattern id="h{k}" class="hatch mp-{k}" patternUnits="userSpaceOnUse" width="7" height="7" '
                   f'patternTransform="rotate(45)"><rect class="hb" width="7" height="7"/>'
                   f'<rect class="hf" width="3.5" height="7"/></pattern>' for k in range(1, PALETTE + 2))
    return (f'<svg class="smap" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}"><defs>{defs}</defs>'
            + "".join(paths) + "".join(texts) + "</svg>"), key


def name_label(label: str, spot: tuple, key: list) -> str:
    """Every settlement gets its name: on one line where it fits, on two where a two-word name fits that way,
    smaller where it then fits, and as a number (with the name in `key`) where the shape is too narrow for any
    of that. The tooltip always has the name."""
    x, y, width = spot
    room = width + 10  # a name may stick out a little
    words = label.split()
    lines = [label]
    if len(label) * LABEL_PX > room and len(words) > 1:  # two lines, split where the halves are most even
        k = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
        lines = [" ".join(words[:k]), " ".join(words[k:])]
    longest = max(len(line) for line in lines)
    if longest * LABEL_PX <= room:
        size = ""
    elif longest * SMALL_PX <= room:
        size = ' class="small"'
    elif width >= NUMBER_MIN:
        size = ' class="small"'
        lines = lines if longest * SMALL_PX <= room + 14 else None
    else:
        lines = None
    if lines is None:
        key.append(label)
        return f'<text x="{x:.1f}" y="{y:.1f}" class="num">{len(key)}</text>'
    if len(lines) == 1:
        return f'<text x="{x:.1f}" y="{y:.1f}"{size}>{escape(lines[0])}</text>'
    step = 10 if size else 12
    return (f'<text x="{x:.1f}" y="{y - step / 2:.1f}"{size}>{escape(lines[0])}</text>'
            f'<text x="{x:.1f}" y="{y + step / 2:.1f}"{size}>{escape(lines[1])}</text>')


def legend(results: dict[str, dict], ranks: dict[int, int], labels: dict[int, str]) -> list[dict]:
    """Which lists lead somewhere, most settlements first: colour class, label, count."""
    counts: dict[int, int] = {}
    for r in results.values():
        if r.get("leader") is not None:
            counts[r["leader"]] = counts.get(r["leader"], 0) + 1
    return [{"cls": f"mp-{min(ranks.get(i, PALETTE + 1), PALETTE + 1)}", "label": labels.get(i, ""), "n": n}
            for i, n in sorted(counts.items(), key=lambda kv: (-kv[1], ranks.get(kv[0], PALETTE + 1)))]
