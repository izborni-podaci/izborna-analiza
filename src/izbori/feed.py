"""Atom feeds, one per language: one entry for each fetch that brought new flags.

Entries live in data/feed.json so the feed survives rebuilds; each keeps the flags as they were when found."""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from izbori.checks import Flag
from izbori.describe import describe
from izbori.history import Archive
from izbori.i18n import PREFIX, check_name, fmt_int, kind_name, latin_page, t
from izbori.translit import latin

KEEP = 200  # entries kept in data/feed.json
SHOW = 30  # flags listed per entry


def path(data_root: Path) -> Path:
    return Path(data_root) / "feed.json"


def load_entries(data_root: Path) -> list[dict]:
    p = path(data_root)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def add_entry(data_root: Path, entry: dict) -> None:
    entries = (load_entries(data_root) + [entry])[-KEEP:]
    path(data_root).write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def make_entry(analysis, new_ids: list[str], when: str) -> dict:
    stations = {s.key: s for s in analysis.round.stations}
    wanted = set(new_ids)
    flags = []
    for f in analysis.flags:
        if f.id not in wanted:
            continue
        s = stations.get(f.station)
        flags.append({"id": f.id, "code": f.code, "station": f.station, "data": f.data,
                      "m": s.municipality if s else "", "mc": s.municipality_code if s else "",
                      "no": s.number if s else f.station.split("/")[-1], "name": s.name if s else ""})
    order = {"paper": 0, "change": 1, "unusual": 2}
    flags.sort(key=lambda x: (order[Flag(x["station"], x["code"]).check.group], x["m"], x["no"]))
    return {"t": when, "round": analysis.round.id, "title": analysis.round.title, "kind": analysis.round.kind,
            "counted": analysis.totals.counted, "total": analysis.totals.stations, "flags": flags}


def contestant_labeller(archive: Archive, rid: str, loc: str):
    meta = archive.meta(rid)
    people = meta.get("contestants") or []

    def label(n: int) -> str:
        c = people[n - 1] if 0 < n <= len(people) else {}
        name = c.get("short") or c.get("name") or ""
        name = latin(name) if loc != "cyr" else name
        return f"{n}. {name}".strip()
    return label


def flag_lines(entry: dict, loc: str, archive: Archive, limit: int | None = SHOW) -> list[str]:
    label = contestant_labeller(archive, entry["round"], loc)
    lines = []
    items = entry["flags"] if limit is None else entry["flags"][:limit]
    for x in items:
        f = Flag(x["station"], x["code"], x["data"])
        place = f"{x['m']}, БМ {x['no']}" if loc != "en" else f"{latin(x['m'])}, station {x['no']}"
        lines.append(f"{place}: {check_name(x['code'], loc)}. {describe(f, loc, label, entry.get('kind', ''))}")
    if limit is not None and len(entry["flags"]) > limit:
        lines.append(t("feed_more", loc, n=fmt_int(len(entry["flags"]) - limit, loc)))
    return lines


def build(data_root: Path, archive: Archive, loc: str, site_url: str) -> str:
    entries = list(reversed(load_entries(data_root)))
    lang = "en" if loc == "en" else "sr"
    feed_url = f"{site_url}feed.{lang}.xml"
    updated = entries[0]["t"] if entries else "2026-01-01T00:00:00+00:00"
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           f'<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="{lang}">',
           f"<title>{escape(t('feed_title', loc))}</title>",
           f"<id>{escape(feed_url)}</id>",
           f"<link rel=\"self\" href={quoteattr(feed_url)}/>",
           f"<link href={quoteattr(site_url + PREFIX[loc])}/>",
           f"<updated>{escape(updated)}</updated>",
           f"<author><name>{escape(t('site_name', loc))}</name></author>"]
    for e in entries:
        title = t("feed_entry", loc, title=f"{kind_name(e.get('kind', ''), loc)} · {e['title']}",
                  n=fmt_int(len(e["flags"]), loc))
        link = f"{site_url}{PREFIX[loc]}r/{e['round']}/check.html"
        progress = t("counted_of", loc, counted=fmt_int(e["counted"], loc), total=fmt_int(e["total"], loc))
        body = "<p>" + escape(progress) + "</p><ul>" + "".join(
            f"<li>{escape(line)}</li>" for line in flag_lines(e, loc, archive)) + "</ul>"
        out += ["<entry>",
                f"<title>{escape(title)}</title>",
                f"<id>{escape(f'{site_url}#{e['round']}-{e['t']}-{lang}')}</id>",
                f"<link href={quoteattr(link)}/>",
                f"<updated>{escape(e['t'])}</updated>",
                f"<content type=\"html\">{escape(body)}</content>",
                "</entry>"]
    out.append("</feed>")
    xml = "\n".join(out) + "\n"
    return latin_page(xml) if loc == "lat" else xml
