"""Small SVG charts drawn at build time. Colours come from site.css classes, so light and dark both work.
Each mark carries a <title>, which browsers show on hover."""

from __future__ import annotations

import math
from html import escape

from markupsafe import Markup

from izbori.i18n import fmt_int, fmt_pct, t
from izbori.stats import Digits


def _nice_step(top: float, ticks: int = 4) -> float:
    raw = top / ticks if top > 0 else 1
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _col(x: float, y: float, w: float, h: float, r: float) -> str:
    """Path for a column with rounded top corners and a square base."""
    r = max(0.0, min(r, w / 2, h))
    return (f"M{x:.2f},{y + h:.2f}V{y + r:.2f}Q{x:.2f},{y:.2f} {x + r:.2f},{y:.2f}"
            f"H{x + w - r:.2f}Q{x + w:.2f},{y:.2f} {x + w:.2f},{y + r:.2f}V{y + h:.2f}Z")


def histogram(bins: list[int], loc: str) -> Markup:
    w, h = 640, 190
    left, right, top, bottom = 40, 20, 10, 24
    pw, ph = w - left - right, h - top - bottom
    n = len(bins)
    peak = max(bins) if bins else 0
    step = _nice_step(peak)
    ymax = max(step, math.ceil(peak / step) * step) if peak else 1
    slot = pw / n
    bar = max(1.0, slot - 2)
    unit = "станица" if loc != "en" else "stations"
    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="{escape(t("hist_heading", loc))}">']
    y = 0
    while y <= ymax + 1e-9:
        yy = top + ph - ph * y / ymax
        parts.append(f'<line class="grid" x1="{left}" x2="{w - right}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="tick" x="{left - 6}" y="{yy + 4:.1f}" text-anchor="end">{fmt_int(int(y), loc)}</text>')
        y += step
    for i, count in enumerate(bins):
        if not count:
            continue
        bh = ph * count / ymax
        x = left + i * slot + (slot - bar) / 2
        label = f"{i}%" if i == 100 else f"{i}–{i + 1}%"
        parts.append(f'<path class="bar" d="{_col(x, top + ph - bh, bar, bh, 1.5)}">'
                     f'<title>{escape(label)}: {fmt_int(count, loc)} {unit}</title></path>')
    parts.append(f'<line class="axis" x1="{left}" x2="{w - right}" y1="{top + ph}" y2="{top + ph}"/>')
    for p in (0, 25, 50, 75, 100):
        x = left + p * slot + slot / 2
        parts.append(f'<text class="tick" x="{x:.1f}" y="{h - 6}" text-anchor="middle">{p}%</text>')
    parts.append("</svg>")
    return Markup("".join(parts))


def digits(d: Digits, loc: str) -> Markup:
    w, h = 300, 140
    left, right, top, bottom = 34, 6, 8, 22
    pw, ph = w - left - right, h - top - bottom
    shares = [c / d.n for c in d.counts]
    ymax = max(0.15, math.ceil(max(shares) * 20) / 20)
    slot = pw / 10
    bar = min(24.0, slot - 6)
    parts = [f'<svg class="chart small" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="{escape(t("digits_heading", loc))}">']
    for y in (0, 0.05, 0.10, 0.15, 0.20, 0.25):
        if y > ymax + 1e-9:
            break
        yy = top + ph - ph * y / ymax
        parts.append(f'<line class="grid" x1="{left}" x2="{w - right}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="tick" x="{left - 5}" y="{yy + 4:.1f}" text-anchor="end">{fmt_pct(y, loc, 0)}</text>')
    for i, share in enumerate(shares):
        bh = ph * share / ymax
        x = left + i * slot + (slot - bar) / 2
        parts.append(f'<path class="bar" d="{_col(x, top + ph - bh, bar, bh, 4)}">'
                     f'<title>{i}: {fmt_pct(share, loc)} ({fmt_int(d.counts[i], loc)})</title></path>')
        parts.append(f'<text class="tick" x="{x + bar / 2:.1f}" y="{h - 6}" text-anchor="middle">{i}</text>')
    ref = top + ph - ph * 0.10 / ymax
    parts.append(f'<line class="ref" x1="{left}" x2="{w - right}" y1="{ref:.1f}" y2="{ref:.1f}"/>')
    parts.append(f'<line class="axis" x1="{left}" x2="{w - right}" y1="{top + ph}" y2="{top + ph}"/>')
    parts.append("</svg>")
    return Markup("".join(parts))
