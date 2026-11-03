"""Observer target list: polling stations ranked as places to watch at the next election.

The ranking comes from public data and is also on the site (Across elections). This command writes it as a
file for observer groups to plan with; their plans (who goes where) stay out of the repository."""

from __future__ import annotations

import csv
import html
from pathlib import Path

from izbori import boards
from izbori.describe import describe
from izbori.history import Archive
from izbori.i18n import check_name, fmt_num, latin_page, t
from izbori.links import safe_url
from izbori.report import analyze, links
from izbori.translit import latin

DECAY = 0.7  # each older round counts 70% of the one after it


def rank(archive: Archive, notes_dir: Path | None = None, rids: list[str] | None = None) -> list[dict]:
    """Places (followed by address, name and number across elections) scored by their flags, newest first. Each row
    names the place's newest station; an older station that was renumbered counts toward the same row."""
    ids = rids or archive.round_ids()
    cache: dict = {}
    rows: dict[str, dict] = {}
    places = links(archive, ids[-1], cache) if ids else None
    for age, rid in enumerate(reversed(ids)):
        a = analyze(archive, rid, notes_dir, cache)
        weight = DECAY ** age
        for key, flags in a.by_station.items():
            p = places.of(rid, key)
            row = rows.setdefault(p.id, {"key": p.newest.key, "score": 0.0, "station": p.newest, "rid": p.rounds[0],
                                         "reasons": [], "notes": []})
            row["score"] += weight * sum(f.check.weight for f in flags)
            row["reasons"].extend((a.round, f) for f in flags)
            row["notes"].extend(a.notes.get(key, []))
    if ids:
        latest = ids[-1]
        ctrl = boards.coverage(boards.load_store(archive.dir(latest)))
        n_lists = len(archive.meta(latest).get("contestants") or [])
        for row in rows.values():
            c = ctrl.get(row["key"]) if row["rid"] == latest else None
            if c is not None and c["lists"] is None:
                c = None
            row["ctrl"] = None if c is None else sorted(int(n) for n, v in c["lists"].items() if v["member"])
            row["ctrl_missing"] = None if c is None else [n for n in range(1, n_lists + 1) if n not in row["ctrl"]]
            row["address"] = c["address"] if c else ""
    return sorted(rows.values(), key=lambda r: (-r["score"], r["key"]))


def _text(s: str, loc: str) -> str:
    return latin(s) if loc != "cyr" else s


def _contestant(rnd, loc):
    def label(n: int) -> str:
        c = rnd.contestants[n - 1] if 0 < n <= len(rnd.contestants) else None
        name = c.label if c else str(n)
        return f"{n}. {_text(name, loc)}"
    return label


def write_csv(rows: list[dict], path: Path, loc: str = "lat") -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["score", "municipality", "municipality_code", "station_no", "station", "address", "flags",
                     "details", "lists_with_member", "lists_without_member", "minutes", "news_notes"])
        for r in rows:
            s = r["station"]
            names = sorted({_text(check_name(f.code, loc), loc) for _, f in r["reasons"]})
            details = [f"[{rnd.id}] " + _text(describe(f, loc, _contestant(rnd, loc), rnd.kind), loc)
                       for rnd, f in r["reasons"]]
            w.writerow([
                f"{r['score']:.1f}",
                _text(s.municipality, loc) if s else "",
                s.municipality_code if s else r["key"].split("/")[0],
                s.number if s else r["key"].split("/")[1],
                _text(s.name, loc) if s else "",
                _text(r.get("address") or "", loc),
                "; ".join(names),
                " | ".join(details),
                "" if r.get("ctrl") is None else " ".join(map(str, r["ctrl"])),
                "" if r.get("ctrl_missing") is None else " ".join(map(str, r["ctrl_missing"])),
                safe_url(s.minutes_url) if s else "",
                " ".join(safe_url(n.url) for n in r["notes"]),
            ])


def write_html(rows: list[dict], path: Path, loc: str = "lat") -> None:
    title = "Lista za posmatrače (poverljivo)" if loc != "en" else "Observer target list (private)"
    by_mun: dict[str, list[dict]] = {}
    for r in rows:
        s = r["station"]
        by_mun.setdefault(_text(s.municipality, loc) if s else r["key"].split("/")[0], []).append(r)
    parts = [f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>",
             "<style>body{font:14px/1.45 system-ui,sans-serif;margin:24px;max-width:900px}"
             "h2{margin-top:28px;border-bottom:1px solid #ccc}table{border-collapse:collapse;width:100%}"
             "td,th{text-align:left;vertical-align:top;padding:4px 6px;border-bottom:1px solid #eee}"
             ".s{font-variant-numeric:tabular-nums;white-space:nowrap}@media print{a{color:inherit}}</style>",
             f"<h1>{html.escape(title)}</h1>",
             "<p>" + html.escape(_text(t("principle", loc), loc)) + "</p>"]
    for mun in sorted(by_mun, key=lambda m: -max(r["score"] for r in by_mun[m])):
        items = by_mun[mun]
        parts.append(f"<h2>{html.escape(mun)}</h2><table><tr><th>BM</th><th>{'Score' if loc == 'en' else 'Skor'}</th>"
                     f"<th>{'Why' if loc == 'en' else 'Zašto'}</th></tr>")
        for r in items:
            s = r["station"]
            why = "".join(
                f"<li>{html.escape(_text(check_name(f.code, loc), loc))}: "
                f"{html.escape(_text(describe(f, loc, _contestant(rnd, loc), rnd.kind), loc))}</li>"
                for rnd, f in r["reasons"])
            link = f" · <a href='{html.escape(safe_url(s.minutes_url))}'>{'minutes' if loc == 'en' else 'zapisnik'}</a>" \
                if s and s.minutes_url else ""
            name = html.escape(_text(s.name, loc)) if s else ""
            parts.append(f"<tr><td class='s'>{html.escape(r['key'].split('/')[1])}</td>"
                         f"<td class='s'>{fmt_num(r['score'], 'en' if loc == 'en' else 'lat')}</td>"
                         f"<td>{name}{link}<ul>{why}</ul></td></tr>")
        parts.append("</table>")
    Path(path).write_text(latin_page("".join(parts)) if loc == "lat" else "".join(parts), encoding="utf-8")
