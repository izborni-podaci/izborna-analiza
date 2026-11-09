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
# the leader's colour is stronger the more it leads with (9 Nov 2026): opacity by the leader's share, in fixed steps
# so maps compare across municipalities: (share under, opacity); the last step has no upper bound
LEAD_STEPS = ((0.40, 0.45), (0.50, 0.65), (0.60, 0.85), (None, 1.0))


def lead_alpha(share: float) -> float:
    return next(a for u, a in LEAD_STEPS if u is None or share < u)


def lead_ramp(pct) -> list[tuple[str, float]]:
    """The steps as the legend names them: ("< 40%", 0.45), ("40–50%", 0.65) … ("≥ 60%", 1.0)."""
    out, low = [], None
    for u, a in LEAD_STEPS:
        out.append((f"< {pct(u)}" if low is None else f"≥ {pct(low)}" if u is None else f"{pct(low)}–{pct(u)}", a))
        low = u
    return out
COLOURS = {"blue": 1, "orange": 2, "green": 3, "yellow": 4, "pink": 5, "darkgreen": 6, "purple": 7, "red": 8}  # --s1 … --s8
COLOURS_FILE = "list_colours.csv"  # round, number, colour, note: the maintainer's colours for a list in an election


def load_colours(path) -> dict[tuple[str, int], int]:
    """(round id, ballot number) → palette slot, from data/list_colours.csv; empty without the file."""
    import csv
    from pathlib import Path
    out = {}
    if path is None or not Path(path).exists():
        return out
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            slot = COLOURS.get((row.get("colour") or "").strip().lower())
            if slot and (row.get("number") or "").strip().isdigit():
                out[((row.get("round") or "").strip(), int(row["number"]))] = slot
    return out


# colours that read as one on a map (on the dark page above all): a slot taken by hand pushes its look-alikes to
# the end of the free slots, so no other list gets one while a distinct colour is left (Pirot 2026: the Student list
# in red, the next list in orange, one colour to the eye)
PREFER = (1, 4, 3, 7, 6, 2, 5, 8)
ALIKE = {8: (2, 5), 2: (8, 4, 5), 5: (8, 2), 1: (7,), 7: (1, 5), 3: (6,), 6: (3,), 4: (2,)}


def slots(ranks: dict[int, int], manual: dict[int, int]) -> dict[int, int]:
    """Each list's palette slot: the maintainer's colour where one is set (manual: list index → slot), and the
    rest by rank in the election over the slots left, the look-alikes of a hand-set colour last; past the palette,
    the "other" slot."""
    out = dict(manual)
    taken = set(manual.values())
    near = {a for k in taken for a in ALIKE.get(k, ())}
    # with colours set by hand the order is no longer the seats', so take the clearest first: yellow and green
    # apart from red and blue for most eyes (red-green blindness included), then the rest
    order = PREFER if manual else range(1, PALETTE + 1)
    free = [k for k in order if k not in taken and k not in near]
    free += [k for k in order if k not in taken and k in near]
    for i in sorted(ranks, key=lambda i: ranks[i]):
        if i in out:
            continue
        out[i] = free.pop(0) if free else PALETTE + 1
    return out


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
                   title: str, pct, width: int = WIDTH, ids: str = "") -> str:
    """The SVG. results: census settlement name → {"leader": list index or None, "share", "second"} (from
    coordinator.by_settlement); ranks: list index → its palette slot (see slots(); 1–8, 9 for "other"); labels: list index →
    display label. Returns the SVG and the key (the names of the settlements too narrow for their name, in the
    order of their numbers); an empty string when there is nothing to draw."""
    to, height = project(features, width)
    if to is None:
        return "", []
    paths, texts, key = [], [], []
    # names are placed widest settlement first; a name whose box would cover one already placed becomes a number
    # with the name in the key (Vranje: 90 settlements, a crowd of names in the south)
    spots = {}
    for f in features:
        label = f["properties"].get("census") or f["properties"].get("name") or ""
        if label:
            spot = label_point(f["geometry"], to)
            if spot:
                spots[id(f)] = (label, spot)
    placed: list[tuple[float, float, float, float]] = []
    numbered: list[tuple[str, tuple]] = []
    for f in sorted(features, key=lambda f: -(spots[id(f)][1][2] if id(f) in spots else 0)):
        if id(f) not in spots:
            continue
        label, spot = spots[id(f)]
        if _lines(label, spot)[0] is None:
            numbered.append((label, spot))
            continue
        box = label_box(label, spot, EXPORT_SCALE)
        if any(_overlap(box, b) for b in placed):
            numbered.append((label, spot))
            continue
        texts.append(name_label(label, spot, []))
        placed.append(box)
    # the numbers read from the top left, row by row, so a reader finds 12 near 11
    for label, spot in sorted(numbered, key=lambda ls: (round(ls[1][1] / 40), ls[1][0])):
        key.append(label)
        texts.append(f'<text x="{spot[0]:.1f}" y="{spot[1]:.1f}" class="num">{len(key)}</text>')
    for f in sorted(features, key=lambda f: f["properties"].get("census") or ""):
        p = f["properties"]
        r = results.get(p.get("census") or "")
        cls, tip, style = "mp-none", escape(p.get("census") or p.get("name") or ""), ""
        if r and r.get("leader") is not None:
            rank = ranks.get(r["leader"], PALETTE + 1)
            cls = f"mp-{min(rank, PALETTE + 1)}"
            if r.get("second") is not None and r["share"] - r["second"] < CLOSE:
                cls += " mp-close"
            tip += f" · {escape(labels.get(r['leader'], ''))} {pct(r['share'])}"
            style = f' style="fill-opacity:{lead_alpha(r["share"])}"'
        paths.append(f'<path class="mp {cls}"{style} d="{path_d(f["geometry"], to)}" data-set="{escape(p.get("census") or "")}">'
                     f"<title>{tip}</title></path>")
    # a close win is hatched in the list's colour rather than painted lighter: two shades of one colour were
    # too alike, and stripes survive print and a dark page
    defs = "".join(f'<pattern id="{ids}h{k}" class="hatch mp-{k}" patternUnits="userSpaceOnUse" width="7" height="7" '
                   f'patternTransform="rotate(45)"><rect class="hb" width="7" height="7"/>'
                   f'<rect class="hf" width="3.5" height="7"/></pattern>' for k in range(1, PALETTE + 2))
    return (f'<svg class="smap" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}"><defs>{defs}</defs>'
            + "".join(paths) + "".join(texts) + "</svg>"), key


def _overlap(a: tuple, b: tuple, gap: float = 1.0) -> bool:
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


EXPORT_SCALE = 1.6  # the shared image draws the map this much larger with names at their size (static/mun.js MAP_K)


def label_box(label: str, spot: tuple, scale: float = 1.0) -> tuple[float, float, float, float] | None:
    """The box name_label's text would take (x0, y0, x1, y1) in drawing units, the text `scale` times smaller than
    its place (the shared image), or None when it would be a number anyway."""
    lines, small = _lines(label, spot)
    if lines is None:
        return None
    px, step = (SMALL_PX, 10) if small else (LABEL_PX, 12)
    w = max(len(line) for line in lines) * px / scale
    h = step * len(lines) / scale
    x, y = spot[0], spot[1]
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def _lines(label: str, spot: tuple) -> tuple[list[str] | None, bool]:
    """name_label's choice: the lines of the name and whether small, or None for a number."""
    x, y, width = spot
    room = width + 10
    words = label.split()
    lines = [label]
    if len(label) * LABEL_PX > room and len(words) > 1:
        k = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
        lines = [" ".join(words[:k]), " ".join(words[k:])]
    longest = max(len(line) for line in lines)
    if longest * LABEL_PX <= room:
        return lines, False
    if longest * SMALL_PX <= room:
        return lines, True
    if width >= NUMBER_MIN and longest * SMALL_PX <= room + 14:
        return lines, True
    return None, False


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
