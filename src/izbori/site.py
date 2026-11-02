"""Static site in Serbian Latin (default), Serbian Cyrillic and English.

Serbian pages are rendered once with Cyrillic text; the Latin pages are the same HTML run through the
transliterator. Links to RIK documents are percent-encoded first, so transliteration never touches them."""

from __future__ import annotations

import re
import shutil
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from izbori import boards, feed, stats, svg
from izbori.checks import BY_CODE, CHECKS, GROUPS, RULES
from izbori.config import REPO_URL, RIK_PUBLIC, SITE_URL
from izbori.contests import Presidential, Proportional, contest_rules
from izbori.describe import describe, field_label
from izbori.history import Archive
from izbori.links import safe_url
from izbori.model import last_url
from izbori.i18n import (LANG_ATTR, LOCALES, PREFIX, check_name, check_rule, fmt_int, fmt_num, fmt_pct,
                         fmt_time, keep, kind_name, latin_page, strip_keep, t)
from izbori.report import Analysis, analyze
from izbori.translit import latin

HERE = Path(__file__).parent
LANG_LABELS = {"lat": "Latinica", "cyr": keep("Ћирилица"), "en": "English"}
SERIES = 8  # categorical colour slots in site.css


class Site:
    def __init__(self, archive: Archive, out: Path, notes_dir: Path | None, site_url: str = SITE_URL):
        self.archive = archive
        self.out = Path(out)
        self.notes_dir = notes_dir
        self.site_url = site_url
        self.env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(),
                               trim_blocks=True, lstrip_blocks=True)
        self.env.filters["url"] = safe_url
        self.env.filters["form"] = lambda label: ((re.search(r"РГ-7-\d+", label or "") or [""])[0]).replace("РГ", "RG")
        self.analyses: dict[str, Analysis] = {}

    # --- helpers handed to templates ---------------------------------------------------------
    def context(self, loc: str, page: str, **extra) -> dict:
        depth = (PREFIX[loc] + page).count("/")
        root = "../" * depth

        def link(target: str) -> str:
            return root + PREFIX[loc] + target

        def name(text: str) -> str:
            return latin(text) if loc == "en" else text

        langs = [{"href": root + PREFIX[other] + page, "label": Markup(LANG_LABELS[other]),
                  "current": other == loc, "lang": LANG_ATTR[other]} for other in LOCALES]
        return {
            "loc": loc, "lang": LANG_ATTR[loc], "root": root, "link": link, "langs": langs, "page": page,
            "t": lambda key, **kw: t(key, loc, **kw), "i": lambda n: fmt_int(n, loc),
            "pct": lambda x, d=1: fmt_pct(x, loc, d), "num": lambda x, d=1: fmt_num(x, loc, d),
            "time": lambda v: fmt_time(v, loc), "name": name, "kind_name": lambda k: kind_name(k, loc),
            "check_name": lambda c: check_name(c, loc), "check_rule": lambda c: check_rule(c, loc, RULES),
            "repo_url": REPO_URL, "rik_url": RIK_PUBLIC, "feed_href": root + ("feed.en.xml" if loc == "en"
                                                                              else "feed.sr.xml"),
            **extra,
        }

    def write(self, loc: str, page: str, template: str, **extra) -> None:
        html = self.env.get_template(template).render(**self.context(loc, page, **extra))
        html = latin_page(html) if loc == "lat" else strip_keep(html)
        path = self.out / (PREFIX[loc] + page)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")

    # --- view models -------------------------------------------------------------------------
    def round_title(self, rnd, loc: str) -> str:
        if loc == "en":
            return self.archive.meta(rnd.id).get("title_en") or latin(rnd.title)
        return rnd.title

    def contestant_label(self, a: Analysis, loc: str):
        def label(n: int) -> str:
            c = a.round.contestants[n - 1] if 0 < n <= len(a.round.contestants) else None
            text = c.label if c else str(n)
            return f"{n}. {latin(text) if loc == 'en' else text}"
        return label

    def flag_view(self, a: Analysis, flags, loc: str) -> list[dict]:
        label = self.contestant_label(a, loc)
        return [{"code": f.code, "group": f.check.group, "name": check_name(f.code, loc),
                 "text": describe(f, loc, label, a.round.kind), "seen": a.flags_seen.get(f.id)} for f in flags]

    def round_view(self, a: Analysis) -> dict:
        rnd = a.round
        totals = a.totals
        rows = []
        order = sorted(range(len(rnd.contestants)), key=lambda i: -totals.votes[i])
        seat_slots = {}
        if isinstance(a.contest, Proportional):
            order.sort(key=lambda i: -a.contest.lists[i].seats)  # most seats first, then most votes
            winners = [i for i in order if a.contest.lists[i].seats]
            seat_slots = {idx: (k + 1 if k < SERIES else 0) for k, idx in enumerate(winners)}
        top_share = max((totals.share_of_voted(i) or 0) for i in range(len(rnd.contestants))) if rnd.contestants else 0
        marker = None
        if isinstance(a.contest, Presidential):
            marker = 0.5
        elif isinstance(a.contest, Proportional):
            marker = contest_rules(rnd).get("threshold", 0.03)
        scale = max(top_share, marker or 0) * 1.05 or 1
        for i in order:
            c = rnd.contestants[i]
            row = {"index": i, "number": c.number, "name": c.name, "label": c.label, "votes": totals.votes[i],
                   "of_voted": totals.share_of_voted(i), "of_valid": totals.share_of_valid(i),
                   "bar": (totals.share_of_voted(i) or 0) / scale, "slot": seat_slots.get(i)}
            if isinstance(a.contest, Proportional):
                lr = a.contest.lists[i]
                row.update({"seats": lr.seats, "status": "over_threshold" if lr.over else
                            "minority" if lr.minority else "under_threshold", "gain": lr.gain, "keep": lr.keep,
                            "takes_part": lr.takes_part})
            rows.append(row)
        view = {"rows": rows, "kind": rnd.kind, "rules": contest_rules(rnd),
                "marker": marker / scale if marker else None}
        if isinstance(a.contest, Proportional):
            p = a.contest
            view["seat_bar"] = [{"slot": seat_slots[i], "seats": p.lists[i].seats, "label": rnd.contestants[i].label,
                                 "number": rnd.contestants[i].number}
                                for i in order if p.lists[i].seats]
            view["threshold_votes"] = p.threshold_votes
            view["seats"] = p.seats
            view["majority"] = p.majority
            view["two_thirds"] = p.two_thirds
        elif isinstance(a.contest, Presidential):
            p = a.contest
            view["pres"] = p
            view["leader"] = rnd.contestants[p.leader] if p.leader is not None else None
            view["runner_up"] = rnd.contestants[p.order[1]] if len(p.order) > 1 else None
        return view

    def municipalities(self, a: Analysis) -> list[dict]:
        by_code: dict[str, list] = defaultdict(list)
        for s in a.round.stations:
            by_code[s.municipality_code].append(s)
        flagged = a.by_station
        out = []
        for code, sts in by_code.items():
            counted = [s for s in sts if s.counted]
            reg = sum(s.registered for s in counted)
            voted = sum(s.voted for s in counted)
            ballots = sum(s.ballots or 0 for s in counted)
            invalid = sum(s.invalid or 0 for s in counted)
            out.append({"code": code, "name": sts[0].municipality, "district": sts[0].district_name,
                        "district_code": sts[0].district_code, "kind": sts[0].kind, "stations": len(sts),
                        "counted": len(counted), "registered": reg, "voted": voted,
                        "turnout": voted / reg if reg else None, "invalid": invalid / ballots if ballots else None,
                        "flagged": sum(1 for s in sts if s.key in flagged)})
        kind_order = {"domestic": 0, "abroad": 1, "prison": 2}
        out.sort(key=lambda m: (kind_order[m["kind"]], m["district_code"], latin(m["name"])))
        return out

    # --- pages -------------------------------------------------------------------------------
    def build(self) -> Path:
        if self.out.exists():
            shutil.rmtree(self.out)
        (self.out / "static").mkdir(parents=True)
        for f in (HERE / "static").iterdir():
            shutil.copy(f, self.out / "static" / f.name)
        (self.out / ".nojekyll").write_text("", encoding="utf-8")
        self.cache: dict = {}
        rids = self.archive.round_ids()
        for rid in rids:
            self.analyses[rid] = analyze(self.archive, rid, self.notes_dir, self.cache)
        rounds = [self.analyses[r] for r in reversed(rids)]
        for loc in LOCALES:
            summaries = [{"id": a.round.id, "title_display": self.round_title(a.round, loc), "kind": a.round.kind,
                          "counted": a.totals.counted, "total": a.totals.stations, "counting": a.counting,
                          "rik_time": a.round.rik_time, "fetched": a.round.fetched,
                          "flagged": len(a.by_station)} for a in rounds]
            self.write(loc, "index.html", "index.html", rounds=summaries)
            self.write(loc, "guide.html", f"guide.{'en' if loc == 'en' else 'sr'}.html")
            self.write(loc, "about.html", "about.html", checks=CHECKS, groups=GROUPS)
            for a in rounds:
                self.round_pages(a, loc)
        # GitHub Pages serves this file for a missing page at any depth, so its links are absolute.
        self.write("lat", "404.html", "404.html", root=self.site_url,
                   link=lambda target: self.site_url + target)
        (self.out / "feed.sr.xml").write_text(feed.build(self.archive.root, self.archive, "lat", self.site_url),
                                              encoding="utf-8")
        (self.out / "feed.en.xml").write_text(feed.build(self.archive.root, self.archive, "en", self.site_url),
                                              encoding="utf-8")
        return self.out

    def round_pages(self, a: Analysis, loc: str) -> None:
        rid = a.round.id
        base = f"r/{rid}/"
        stations = {s.key: s for s in a.round.stations}
        by_station = a.by_station
        municipalities = self.municipalities(a)
        view = self.round_view(a)
        totals = a.totals
        top2 = stats.top_two(totals.votes) if totals.votes else []
        label = self.contestant_label(a, loc)
        context_stats = {
            "hist": svg.histogram(stats.turnout_histogram(a.round), loc),
            "digits": [(label(i + 1), d, svg.digits(d, loc)) for i in top2
                       if (d := stats.last_digits(a.round, i)) is not None],
            "round": stats.round_percentages(a.round, top2),
            "corr": [(label(i + 1), stats.correlation(a.round, i)) for i in top2],
            "labels": {str(i): label(i + 1) for i in top2},
        }
        register = None
        same_kind = [r for r in a.previous if self.archive.meta(r).get("kind") == a.round.kind]
        if same_kind:
            prev = self.cache.get(same_kind[0]) or self.archive.load(same_kind[0])
            national, rows = stats.register_changes(a.round, prev)
            if rows:
                register = {"title": self.round_title(prev, loc), "national": national, "rows": rows[:20]}
        context_stats["register"] = register
        counts = defaultdict(int)
        for f in a.flags:
            counts[f.code] += 1
        group_counts = {g: len({f.station for f in a.flags if f.check.group == g}) for g in GROUPS}
        ctrl = boards.coverage(boards.load_store(self.archive.dir(rid)))
        ctrl_table, ctrl_readable = ctrl_rows(a.round.contestants, ctrl.values())
        common = {"rebuilt": self.archive.meta(rid).get("source") == "results_app",
                  "ctrl_readable": ctrl_readable, "a": a, "rnd": a.round, "totals": totals, "base": base, "view": view,
                  "snapshots": a.snapshots, "label": label, "rtitle": self.round_title(a.round, loc),
                  "ctrl": ctrl, "ctrl_known": bool(ctrl), "ctrl_table": ctrl_table}
        self.write(loc, base + "index.html", "round.html", municipalities=municipalities, stats=context_stats,
                   counts=counts, group_counts=group_counts, checks=CHECKS, groups=GROUPS, **common)

        # flagged stations, strongest group first, then by total weight
        group_rank = {g: i for i, g in enumerate(GROUPS)}
        items = []
        for key, flags in by_station.items():
            s = stations.get(key)
            seen = [a.flags_seen.get(f.id) for f in flags if a.flags_seen.get(f.id)]
            items.append({
                "key": key, "s": s, "flags": self.flag_view(a, flags, loc),
                "types": " ".join(sorted({f.code for f in flags})),
                "rank": (min(group_rank[f.check.group] for f in flags), -sum(f.check.weight for f in flags)),
                "seen": min(seen) if seen else None, "notes": a.notes.get(key, []),
                "mun": s.municipality_code if s else key.split("/")[0],
            })
        items.sort(key=lambda x: (x["rank"], latin(x["s"].municipality) if x["s"] else "", int(x["s"].number)
                                  if x["s"] and x["s"].number.isdigit() else 0))
        mun_options = sorted({(m["code"], m["name"]) for m in municipalities if m["flagged"]},
                             key=lambda m: latin(m[1]))
        self.write(loc, base + "check.html", "check.html", items=items, mun_options=mun_options, checks=CHECKS,
                   groups=GROUPS, counts=counts, **common)

        changes = []
        for e in reversed(a.changes):
            s = stations.get(e["s"])
            value = lambda v: "" if v is None else v  # noqa: E731
            is_link = e["f"] in ("zapisnik_link", "korekcija_dokument_link")
            changes.append({"t": e["t"], "s": s, "key": e["s"], "field": field_label(e["f"], loc, a.round.kind),
                            "before": "" if is_link else value(e["o"]), "now": "" if is_link else value(e["n"]),
                            "before_url": safe_url(last_url(e["o"])) if is_link and e["o"] else "",
                            "now_url": safe_url(last_url(e["n"])) if is_link and e["n"] else ""})
        self.write(loc, base + "changes.html", "changes.html", changes=changes, **common)

        by_code: dict[str, list] = defaultdict(list)
        for s in a.round.stations:
            by_code[s.municipality_code].append(s)
        for m in municipalities:
            sts = sorted(by_code[m["code"]], key=lambda s: (int(s.number) if s.number.isdigit() else 0, s.number))
            rows = [{"s": s, "flags": self.flag_view(a, by_station.get(s.key, []), loc),
                     "notes": a.notes.get(s.key, [])} for s in sts]
            votes = [sum((s.votes[i] or 0) for s in sts if s.counted) for i in range(len(a.round.contestants))]
            mctrl, mreadable = ctrl_rows(a.round.contestants, [ctrl[s.key] for s in sts if s.key in ctrl])
            self.write(loc, base + f"m/{m['code']}.html", "municipality.html", m=m, rows=rows, mvotes=votes,
                       mctrl=mctrl, mreadable=mreadable, **common)


def ctrl_rows(contestants, coverage) -> tuple[list[dict], int]:
    """Per list: at how many stations it had a member and a deputy on the extended board, most first."""
    readable = [v for v in coverage if v["lists"] is not None]
    rows = []
    for c in contestants:
        got = [v["lists"].get(str(c.number), {}) for v in readable]
        members = sum(1 for g in got if g.get("member"))
        deputies = sum(1 for g in got if g.get("deputy"))
        rows.append({"number": c.number, "label": c.label, "members": members, "deputies": deputies,
                     "total": members + deputies})
    rows.sort(key=lambda r: (-r["total"], -r["members"], r["number"]))
    top = max((r["total"] for r in rows), default=0)
    for r in rows:
        r["bar"] = r["total"] / top if top else 0
    return rows, len(readable)


def build(archive: Archive, out: Path, notes_dir: Path | None, site_url: str = SITE_URL) -> Path:
    return Site(archive, out, notes_dir, site_url).build()
