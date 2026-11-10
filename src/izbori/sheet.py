"""A reading sheet for the boards' minutes filled in by hand: each station's number cells side by side, one row per
station, with what a digit model reads in each, so a person reads a municipality's results from a few images and
checks the model's guesses instead of copying every figure from a whole page.

The cells are found by the form's ruled lines: the results table's right column (turnout, ballots in the box,
invalid, valid, a heading row, a header row, then one row per list) and, on the registered voters' band, its
largest cell. Only those cells reach the sheet: no text of the minutes at all. A station whose cells aren't found
as the rest are keeps its crops instead, to be read whole.

The guesses are help, not data. Measured on Temerin 2024 and Sečanj 2025 (48 stations read by eye) a model trained
on MNIST read about two thirds of the cells right, and a station's figures that add up were still wrong in about
half the cases, so nothing is ever taken from a guess: a person writes every figure into data/local_hand.csv.
A guess is marked where its station doesn't add up, to show where to look closer.

Needs numpy, opencv and scikit-learn, which the project doesn't install: the workflow runs this with `uv run --with`.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import math
import re
import urllib.request
from collections import Counter
from pathlib import Path

# MNIST's training set, from a mirror on GitHub (the original site isn't reachable from everywhere), checked
# against the original files' digests
MNIST = "https://raw.githubusercontent.com/fgnt/mnist/master/"
MNIST_FILES = {"train-images-idx3-ubyte.gz": "440fcabf73cc546fa21475e81ea370265605f56be210a4024d2ca8f203523609",
               "train-labels-idx1-ubyte.gz": "3552534a0a558bbed6aed32b30c495cca23d567ec52cac8be1a0730e8010255c"}
FIELDS = ("upisani", "izašli", "kutija", "nevažeći", "važeći")  # then the lists, 1..k
TABLE_EXTRA = 6  # turnout, ballots, invalid, valid, the lists' heading row and their header row
CELL_H = 64  # a cell's height on the sheet
ROWS_PER_SHEET = 12
CROP = re.compile(r"^(?P<stem>.+)-p(?P<page>\d+)-(?P<n>\d+)\.png$")


# --- the cells ---------------------------------------------------------------------------------------------------

def _runs(profile, threshold) -> list[int]:
    """Centres of the runs where profile reaches threshold."""
    out, start = [], None
    for i, v in enumerate(list(profile) + [0]):
        if v >= threshold and start is None:
            start = i
        elif v < threshold and start is not None:
            out.append((start + i - 1) // 2)
            start = None
    return out


def ruled_cells(gray) -> list[tuple[int, int, int, int]]:
    """The cells of a table's rightmost column as (top, bottom, left, right), top to bottom, from its ruled lines
    (a scan's slight tilt allowed for)."""
    import cv2
    bw = cv2.adaptiveThreshold(255 - gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, -2)
    h, w = bw.shape
    hor = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, w // 12), 1)))
    ver = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, h // 25))))
    ver = cv2.dilate(ver, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1)))
    # a ruled line runs most of the crop's height (a digit's stroke doesn't); the scan's own edge isn't one
    xs = [x for x in _runs((ver > 0).sum(0), h * 0.5) if w * 0.5 < x < w - 20]
    if len(xs) < 2:
        return []
    x1 = xs[-1]
    x0 = max([x for x in xs if x < x1 - w * 0.08] or [xs[0]])
    hor = cv2.dilate(hor, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 7)))
    ys = _runs((hor[:, x0 + 8:x1 - 8] > 0).sum(1), (x1 - x0) * 0.6)
    return [(a, b, x0, x1) for a, b in zip(ys, ys[1:]) if b - a >= 60]  # lower: a heading's box


def cell_ink(gray, cell, margin: int = 10):
    """A cell's handwriting as white on black, without the stubs of its ruled lines."""
    import cv2
    import numpy as np
    a, b, x0, x1 = cell
    c = gray[a + margin:b - margin, x0 + margin:x1 - margin]
    _, bw = cv2.threshold(c, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = bw.shape
    hor = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w // 3), 1)))
    ver = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, int(h * .8)))))
    bw = cv2.subtract(bw, cv2.bitwise_or(hor, ver))
    n, lab, st, _ = cv2.connectedComponentsWithStats(bw)
    keep = np.zeros_like(bw)
    for i in range(1, n):
        x, y, cw, ch, area = st[i]
        edge = y <= 1 or y + ch >= h - 1 or x <= 1 or x + cw >= w - 1
        if area >= 25 and not (edge and min(cw, ch) <= 8):
            keep[lab == i] = 255
    return keep


# --- the digits --------------------------------------------------------------------------------------------------

def digit_model(cache: Path):
    """A small network trained on MNIST (and a thickened copy, as a pen on a scan is), kept in cache."""
    import pickle
    import numpy as np
    cache.mkdir(parents=True, exist_ok=True)
    saved = cache / "digits.pkl"
    if saved.exists():
        return pickle.loads(saved.read_bytes())
    data = {}
    for name, digest in MNIST_FILES.items():
        p = cache / name
        if not p.exists():
            with urllib.request.urlopen(MNIST + name, timeout=120) as r:
                p.write_bytes(r.read())
        if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            p.unlink()
            raise ValueError(f"{name}: not MNIST's file")
        data[name] = gzip.decompress(p.read_bytes())
    import cv2
    from sklearn.neural_network import MLPClassifier
    x = np.frombuffer(data["train-images-idx3-ubyte.gz"], np.uint8, offset=16).reshape(-1, 28, 28)
    y = np.frombuffer(data["train-labels-idx1-ubyte.gz"], np.uint8, offset=8)
    thick = np.stack([cv2.dilate(i, np.ones((2, 2), np.uint8)) for i in x])
    model = MLPClassifier((256, 128), max_iter=12, random_state=0)
    model.fit(np.concatenate([x, thick]).reshape(-1, 784) / 255.0, np.concatenate([y, y]))
    saved.write_bytes(pickle.dumps(model))
    return model


def glyphs(bw) -> list:
    """A cell's ink split into digits: its connected parts, those overlapping across merged (a 7's bar)."""
    import cv2
    import numpy as np
    n, lab, st, _ = cv2.connectedComponentsWithStats(bw)
    parts = [[st[i, 0], st[i, 0] + st[i, 2], [i]] for i in range(1, n) if st[i, 4] >= 25]
    if not parts:
        return []
    tall = max(st[i, 3] for p in parts for i in p[2])
    parts = sorted(p for p in parts if max(st[i, 3] for i in p[2]) >= tall * .25 or p[1] - p[0] >= tall * .4)
    merged: list = []
    for p in parts:
        if merged and p[0] < merged[-1][1] - .35 * min(p[1] - p[0], merged[-1][1] - merged[-1][0]):
            merged[-1][1] = max(merged[-1][1], p[1])
            merged[-1][2] += p[2]
        else:
            merged.append(p)
    return [(np.isin(lab, ids).astype(np.uint8) * 255)[:, x0:x1] for x0, x1, ids in merged]


def mnist_like(glyph):
    """A digit fitted in 20×20 and centred by its mass in 28×28, as MNIST's are."""
    import cv2
    import numpy as np
    ys, xs = np.nonzero(glyph)
    g = glyph[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    s = 20.0 / max(g.shape)
    g = cv2.resize(g, (max(1, round(g.shape[1] * s)), max(1, round(g.shape[0] * s))), interpolation=cv2.INTER_AREA)
    out = np.zeros((28, 28), np.float32)
    y0, x0 = (28 - g.shape[0]) // 2, (28 - g.shape[1]) // 2
    out[y0:y0 + g.shape[0], x0:x0 + g.shape[1]] = g
    m = cv2.moments(out)
    if m["m00"]:
        shift = np.float32([[1, 0, 14 - m["m10"] / m["m00"]], [0, 1, 14 - m["m01"] / m["m00"]]])
        out = cv2.warpAffine(out, shift, (28, 28))
    return out / max(float(out.max()), 1.0)


def readings(probs, top: int = 3, keep: int = 10) -> list[tuple[int, float]]:
    """A cell's likeliest values as (value, log probability), best first, from each digit's probabilities; one
    digit may be a stray mark, so each reading without it is a candidate too, at a cost. An empty cell reads 0."""
    import itertools
    if len(probs) == 0:
        return [(0, math.log(.5))]
    per = [sorted(((math.log(max(float(p[d]), 1e-6)), d) for d in range(10)), reverse=True)[:top] for p in probs]
    options = [(per, 0.0)] + ([(per[:i] + per[i + 1:], math.log(.05)) for i in range(len(per))] if len(per) > 1
                               else [])
    best: dict[int, float] = {}
    for digits, cost in options:
        for combo in itertools.product(*digits):
            v = int("".join(str(d) for _, d in combo))
            s = sum(x for x, _ in combo) + cost
            if s > best.get(v, -math.inf):
                best[v] = s
    return sorted(best.items(), key=lambda vs: -vs[1])[:keep]


def adds_up(values: list[int], k: int) -> bool:
    """registered, turnout, ballots, invalid, valid and k lists' votes: ballots less invalid are the valid votes,
    the lists add up to them, and no more ballots than voters, nor voters than registered."""
    if len(values) != 5 + k or any(v is None for v in values):
        return False
    reg, voted, ballots, invalid, valid = values[:5]
    return ballots - invalid == valid and sum(values[5:]) == valid and ballots <= voted <= reg


# --- the sheet ---------------------------------------------------------------------------------------------------

def station_crops(crops: Path) -> dict[str, list[Path]]:
    """Each minutes' crops (named <stem>-p<page>-<n>.png by local.crop_results), in order."""
    out: dict[str, list[Path]] = {}
    for p in sorted(crops.glob("*.png")):
        m = CROP.match(p.name)
        if m:
            out.setdefault(m["stem"], []).append(p)
    for stem in out:
        out[stem].sort(key=lambda p: (int(CROP.match(p.name)["page"]), int(CROP.match(p.name)["n"])))
    return out


def lists_count(tables: dict[str, list]) -> int:
    """The lists on the form: the results tables' most common count of cells, less turnout, ballots, invalid,
    valid and the two heading rows."""
    counts = Counter(len(c) for c in tables.values() if len(c) > TABLE_EXTRA)
    return counts.most_common(1)[0][0] - TABLE_EXTRA if counts else 0


def short_names(stems: list[str]) -> dict[str, str]:
    """Stems without what most of them begin with (80446-zapisnik-o-radu-birackog-odbora-lo12 → lo12)."""
    import os
    heads = Counter(s.rsplit("-", 1)[0] + "-" if "-" in s else "" for s in stems)
    common = os.path.commonprefix([s for s in stems if s.startswith(heads.most_common(1)[0][0])]) if stems else ""
    common = common[:common.rfind("-") + 1] if "-" in common else ""
    out = {}
    for s in stems:
        name = s[len(common):] if s.startswith(common) and s != common else s
        out[s] = name if len(name) <= 18 else name[:17] + "…"
    return out


def make_sheets(crops: Path, out: Path, model=None, log=print) -> dict:
    """Sheets of the number cells of every minutes in crops, into out (sheet-<n>.png and guesses.csv), with the
    crops of minutes whose cells weren't found copied to out/whole/. Returns what was made."""
    import shutil
    import cv2
    import numpy as np
    out.mkdir(parents=True, exist_ok=True)
    found: dict[str, tuple] = {}
    for stem, paths in station_crops(crops).items():
        grays = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths]
        cells = [ruled_cells(g) for g in grays]
        t = max(range(len(paths)), key=lambda i: len(cells[i]))  # the results table: the crop with most cells
        band = next((i for i in range(len(paths)) if i != t), None)  # the registered voters' band
        found[stem] = (paths, grays, cells, t, band)
    k = lists_count({s: f[2][f[3]] for s, f in found.items()})
    names = short_names(list(found))
    rows, whole = [], []
    for stem, (paths, grays, cells, t, band) in found.items():
        table = cells[t]
        if k == 0 or len(table) != TABLE_EXTRA + k or band is None:
            whole.append(stem)
            continue
        reg = cells[band]
        reg_ink = cell_ink(grays[band], max(reg, key=lambda c: c[1] - c[0])) if reg else None
        band_whole = reg_ink is None or not reg_ink.any()
        if band_whole:  # no ruled cell with ink: the band's right part as it is (the figure and the date)
            g = grays[band]
            reg_ink = 255 - g[:, int(g.shape[1] * .55):]
        inks = [reg_ink] + [cell_ink(grays[t], c) for c in table[:4] + table[-k:]]
        guesses = []
        for i, ink in enumerate(inks):
            if model is None or not ink.any() or (i == 0 and band_whole):
                guesses.append(None)
                continue
            gs = glyphs(ink)
            probs = model.predict_proba(np.stack([mnist_like(g).reshape(-1) for g in gs])) if gs else []
            guesses.append(readings(probs)[0][0])
        rows.append((stem, inks, guesses))
    for stem in whole:
        (out / "whole").mkdir(exist_ok=True)
        for p in found[stem][0]:
            shutil.copy(p, out / "whole" / p.name)
    rows.sort(key=lambda r: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", names[r[0]])])
    header = list(FIELDS) + [f"lista {i}" for i in range(1, k + 1)]
    with open(out / "guesses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["minutes", *header, "adds_up"])
        for stem, _, guesses in rows:
            w.writerow([names[stem], *("" if g is None else g for g in guesses), adds_up(guesses, k)])
    sheets = []
    for n in range(0, len(rows), ROWS_PER_SHEET):
        img = _draw(rows[n:n + ROWS_PER_SHEET], header, names, k)
        p = out / f"sheet-{n // ROWS_PER_SHEET + 1}.png"
        cv2.imwrite(str(p), img)
        sheets.append(p)
    log(f"{len(rows)} minutes on {len(sheets)} sheet(s), {k} lists; read whole: {', '.join(names[s] for s in whole) or 'none'}")
    return {"lists": k, "rows": len(rows), "sheets": sheets, "whole": [names[s] for s in whole]}


def _draw(rows, header, names, k):
    """One sheet: a header row of the fields, then per station its name and cells, each with the guess under it
    (red where the station doesn't add up)."""
    import cv2
    import numpy as np
    label_w, gap, guess_h = 230, 28, 26
    widths = [0] * len(header)
    scaled = []
    for _, inks, _ in rows:
        cells = []
        for i, ink in enumerate(inks):
            ys, xs = np.nonzero(ink)
            c = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(xs) else np.zeros((10, 10), np.uint8)
            # scaled by the ink's height, but a short mark (a dash) not blown up to a digit's size
            s = (CELL_H - 8) / max(c.shape[0], .4 * ink.shape[0], 1)
            c = cv2.resize(c, (max(1, int(c.shape[1] * s)), max(1, int(c.shape[0] * s))), interpolation=cv2.INTER_AREA)
            c = cv2.copyMakeBorder(c, 0, CELL_H - 8 - c.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=0)
            c = c[:, :420]
            cells.append(c)
            widths[i] = max(widths[i], c.shape[1], 90)
        scaled.append(cells)
    row_h = CELL_H + guess_h + 6
    W = label_w + sum(w + gap for w in widths) + gap
    H = 40 + row_h * len(rows)
    img = np.full((H, W, 3), 255, np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    x = label_w
    for i, name in enumerate(header):
        cv2.putText(img, _ascii(name), (x + 2, 26), font, .6, (90, 90, 90), 1, cv2.LINE_AA)
        x += widths[i] + gap
    for r, ((stem, _, guesses), cells) in enumerate(zip(rows, scaled)):
        y = 40 + r * row_h
        ok = adds_up(guesses, k)
        cv2.line(img, (0, y), (W, y), (200, 200, 200), 1)
        cv2.putText(img, _ascii(names[stem]), (8, y + CELL_H // 2 + 8), font, .6, (0, 0, 0), 2, cv2.LINE_AA)
        x = label_w
        for i, c in enumerate(cells):
            cv2.line(img, (x - gap // 2, y), (x - gap // 2, y + row_h), (225, 225, 225), 1)
            tile = cv2.cvtColor(255 - c, cv2.COLOR_GRAY2BGR)
            img[y + 4:y + 4 + tile.shape[0], x:x + tile.shape[1]] = tile
            g = guesses[i]
            if not c.any():
                cv2.putText(img, "(prazno)", (x + 2, y + CELL_H // 2), font, .55, (150, 150, 150), 1, cv2.LINE_AA)
            elif g is not None:
                cv2.putText(img, str(g), (x + 2, y + CELL_H + guess_h - 6), font, .65,
                            (40, 140, 40) if ok else (30, 30, 210), 1, cv2.LINE_AA)
            x += widths[i] + gap
    return img


def _ascii(s: str) -> str:
    """OpenCV draws ASCII only."""
    return s.translate(str.maketrans("šđčćžŠĐČĆŽ…", "sdcczSDCCZ~"))
