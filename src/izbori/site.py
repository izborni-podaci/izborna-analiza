"""Static site in Serbian Latin (default), Serbian Cyrillic and English.

Serbian pages are rendered once with Cyrillic text; the Latin pages are the same HTML run through the
transliterator. Links to RIK documents are percent-encoded first, so transliteration never touches them."""

from __future__ import annotations

import re
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from izbori import boards, feed, repeat, stats, svg
from izbori.checks import BY_CODE, CHECKS, GROUPS, RULES
from izbori.config import REPO_URL, RIK_PUBLIC, SITE_URL
from izbori.contests import Presidential, Proportional, contest_rules
from izbori.describe import describe, field_label
from izbori.history import Archive
from izbori.links import safe_url
from izbori.model import last_url
from izbori.i18n import (LANG_ATTR, LOCALES, MONTHS_EN, PREFIX, check_name, check_rule, fmt_int, fmt_num, fmt_pct,
                         fmt_time, keep, kind_name, latin_page, strip_keep, t)
from izbori import narrative
from izbori.places import Place, follow
from izbori.report import Analysis, analyze
from izbori.translit import latin

HERE = Path(__file__).parent
LANG_LABELS = {"lat": "Latinica", "cyr": keep("Ћирилица"), "en": "English"}
SERIES = 8  # categorical colour slots in site.css
LOOKALIKE = str.maketrans("AaEeOoPpCcXxKkMHTBy", "АаЕеОоРрСсХхКкМНТВу")  # Latin letters RIK sometimes types for Cyrillic


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
    def st_path(self, rid: str, key: str) -> str:
        """The page of the place a round's station belongs to: that place in every election in the archive."""
        p = self.places.of(rid, key)
        return f"s/{p.id}.html" if p else ""

    def ctrl_of(self, rid: str) -> dict:
        if rid not in self.ctrl_cache:
            self.ctrl_cache[rid] = boards.coverage(boards.load_store(self.archive.dir(rid)))
        return self.ctrl_cache[rid]

    def flagged_in(self, p: Place) -> int:
        """In how many of its elections the place had at least one flag."""
        return sum(1 for rid in p.rounds if p.stations[rid].key in self.flagged[rid])

    def top_three(self, rid: str, votes: list) -> list[dict]:
        """The three contestants with most votes, with their share of valid votes."""
        total = sum(v or 0 for v in votes)
        if not total:
            return []
        contestants, labels = self.analyses[rid].round.contestants, self.labels[rid]
        order = sorted(range(len(votes)), key=lambda i: -(votes[i] or 0))[:3]
        return [{"number": contestants[i].number, "label": labels[i], "full": contestants[i].name,
                 "share": (votes[i] or 0) / total} for i in order if votes[i]]

    def place_pages(self, loc: str, cols: dict) -> None:
        """One page for every polling place: a few sentences about it, then one row per election it took part in,
        newest first, every election alike, each linking to the station's row in that election."""
        group_of = {c.code: c.group for c in CHECKS}
        for p in self.places.places:
            rows, codes, story = [], set(), []
            for rid in p.rounds:
                a, s = self.analyses[rid], p.stations[rid]
                flags = self.flagged[rid].get(s.key, [])
                codes.update(f.code for f in flags)
                ctrl = self.ctrl_of(rid)
                rows.append({"rid": rid, "short": cols[rid]["short"], "date": fmt_date(self.dates[rid], loc), "s": s,
                             "how": p.how[rid] if s.number != p.newest.number else "",
                             "address": p.addresses.get(rid, ""), "flags": self.flag_view(a, flags, loc),
                             "notes": a.notes.get(s.key, []), "ctrl": ctrl.get(s.key), "ctrl_known": bool(ctrl),
                             "n_lists": len(a.round.contestants),
                             "top": self.top_three(rid, s.votes) if s.counted else []})
                story.append(self.place_election(rid, s, flags, cols[rid]["short"]))
            hints = sorted(codes, key=strength)
            self.write(loc, f"s/{p.id}.html", "station.html", p=p, s=p.newest, rows=rows, address=p.address,
                       hints=hints, group_of=group_of,
                       analysis=narrative.place(story, [cols[r]["short"] for r in self.mun_rounds[p.code]
                                                        if r not in p.stations], loc))

    def place_election(self, rid: str, s, flags: list, short: str) -> narrative.Election:
        """One election at a polling place, next to its municipality in the same election."""
        m, mv = self.mun_rows[rid][s.municipality_code], self.mun_votes[rid][s.municipality_code]
        e = narrative.Election(short=short, number=s.number, name=s.name,
                               flags=sorted(dict.fromkeys(f.code for f in flags), key=strength),
                               ref_turnout=m["turnout"], ref_invalid=m["invalid"])
        if s.counted:
            e.registered, e.turnout, e.invalid = s.registered, s.turnout, s.invalid_share
            here, there = leading(s.votes), leading(mv)
            if here is not None:
                e.leader = self.labels[rid][here]
                e.leader_share = (s.votes[here] or 0) / sum(v or 0 for v in s.votes)
                e.ref_leader_share = mv[here] / sum(mv) if sum(mv) else None
                e.same_leader = here == there if there is not None else None
        return e

    def municipality_election(self, rid: str, code: str, short: str) -> narrative.Election:
        """One election in a municipality, next to the whole election."""
        totals, m, mv = self.analyses[rid].totals, self.mun_rows[rid][code], self.mun_votes[rid][code]
        e = narrative.Election(short=short, registered=m["registered"], turnout=m["turnout"], invalid=m["invalid"],
                               ref_turnout=totals.turnout, ref_invalid=totals.invalid_share, stations=m["stations"],
                               flagged=m["flagged"],
                               ref_flagged=len(self.flagged[rid]) / totals.stations if totals.stations else None)
        here, there = leading(mv), leading(totals.votes)
        if here is not None:
            e.leader = self.labels[rid][here]
            e.leader_share = mv[here] / sum(mv)
            e.ref_leader_share = totals.share_of_valid(here)
            e.same_leader = here == there if there is not None else None
        return e

    def municipality_history_pages(self, loc: str, cols: dict) -> None:
        """One page per municipality: one row per election it took part in, newest first, each linking to the
        municipality in that election; then its polling places, each linking to its page across elections."""
        newest_first = list(reversed(self.rids))
        by_code: dict[str, list[Place]] = defaultdict(list)
        for p in self.places.places:
            by_code[p.code].append(p)
        for code, rids in self.mun_rounds.items():
            newest = self.mun_rows[rids[0]][code]
            rows = [{"rid": rid, "short": cols[rid]["short"], "date": fmt_date(self.dates[rid], loc),
                     "m": self.mun_rows[rid][code], "top": self.top_three(rid, self.mun_votes[rid][code])}
                    for rid in rids]
            places = []
            for p in by_code[code]:
                s = p.newest
                places.append({"id": p.id, "number": s.number, "name": s.name, "former": p.former_numbers,
                               "n": len(p.rounds), "k": self.flagged_in(p),
                               "last": cols[p.rounds[0]]["short"] if p.rounds[0] != rids[0] else "",
                               "order": (p.rounds[0] != rids[0], int(s.number) if s.number.isdigit() else 10 ** 9,
                                         s.number, newest_first.index(p.rounds[0]))})
            places.sort(key=lambda x: x["order"])
            mine = by_code[code]
            repeat = (sum(1 for x in places if x["k"] >= 1), sum(1 for x in places if x["k"] >= 2))
            network = (sum(1 for p in mine if p.rounds == [rids[0]]),
                       sum(1 for p in mine if rids[0] not in p.stations),
                       sum(1 for p in mine if rids[0] in p.stations and p.former_numbers))
            analysis = narrative.municipality([self.municipality_election(rid, code, cols[rid]["short"]) for rid in rids],
                                              [cols[r]["short"] for r in newest_first if r not in rids], repeat, network,
                                              loc)
            self.write(loc, f"m/{code}.html", "municipality_history.html", code=code, mname=newest["name"],
                       district=newest["district"] if newest["kind"] == "domestic" else "", rows=rows, places=places,
                       analysis=analysis)

    def write_search(self, loc: str) -> None:
        """search.json for the search on the home page, kept small. Municipalities: [name, code, elections]. Polling
        places: [municipality, number, name, page, elections flagged, elections, former numbers], flagged ones first;
        page is left out ("") when it is the municipality code and number. Both lead to their pages across all
        elections; the page builds the labels and links."""
        conv = (lambda text: text) if loc == "cyr" else latin
        names = {code: self.mun_rows[rids[0]][code]["name"] for code, rids in self.mun_rounds.items()}
        order = sorted(names, key=lambda code: latin(names[code]))
        at = {code: i for i, code in enumerate(order)}
        rows = []
        for p in self.places.places:
            s, k = p.newest, self.flagged_in(p)
            page = "" if p.id == station_path(s.key)[2:-5] else p.id
            rows.append((-k, latin(names[p.code]), int(s.number) if s.number.isdigit() else 0, s.number,
                         [at[p.code], s.number, conv(s.name), page, k, len(p.rounds), ", ".join(p.former_numbers)]))
        rows.sort(key=lambda r: r[:4])
        data = {"m": [[conv(names[c]), c, len(self.mun_rounds[c])] for c in order], "s": [r[4] for r in rows]}
        path = self.out / (PREFIX[loc] + "search.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def short_title(self, rnd, loc: str) -> str:
        year = (self.archive.meta(rnd.id).get("date") or "")[:4]
        if rnd.kind in ("presidential", "parliamentary", "provincial", "local") and year:
            return f"{t('short_' + rnd.kind, loc)} {year}"
        return self.round_title(rnd, loc)

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
            out[-1]["flagged_share"] = out[-1]["flagged"] / len(sts) if sts else None
        kind_order = {"domestic": 0, "abroad": 1, "prison": 2}
        out.sort(key=lambda m: (kind_order[m["kind"]], m["district_code"], latin(m["name"])))
        return out

    # --- pages -------------------------------------------------------------------------------
    def build(self) -> Path:
        if self.out.exists():
            shutil.rmtree(self.out)
        (self.out / "static").mkdir(parents=True)
        shutil.copytree(HERE / "static", self.out / "static", dirs_exist_ok=True)
        (self.out / ".nojekyll").write_text("", encoding="utf-8")
        self.cache: dict = {}
        self.ctrl_cache: dict = {}
        rids = self.archive.round_ids()
        for rid in rids:
            self.analyses[rid] = analyze(self.archive, rid, self.notes_dir, self.cache)
        rounds = [self.analyses[r] for r in reversed(rids)]
        oldest_first = [self.analyses[r] for r in rids]
        rep_rows, rep_once = repeat.stations(oldest_first)
        rep_muns, national = repeat.municipalities(oldest_first)
        rep_same = repeat.same_counts(rep_rows)
        rep_n2 = sum(1 for r in rep_rows if r["k"] >= 2)
        places, by_code = set(), defaultdict(set)
        for a in oldest_first:
            places.update(s.key for s in a.round.stations)
            for key, flags in a.by_station.items():
                for f in flags:
                    by_code[f.code].add(key)
        overall = {"flagged": len(rep_rows), "total": len(places), "repeated": rep_n2,
                   "counts": {code: len(keys) for code, keys in by_code.items()}}
        group_of = {c.code: c.group for c in CHECKS}
        # the same polling place and municipality across elections, for the search and the pages across elections
        self.rids = rids
        self.dates = {rid: self.archive.meta(rid).get("date") for rid in rids}
        self.flagged = {a.round.id: a.by_station for a in oldest_first}
        self.labels = {a.round.id: display_labels(a.round.contestants) for a in oldest_first}
        self.places = follow([(a.round.id, a.round.stations, boards.addresses(boards.load_store(self.archive.dir(a.round.id))))
                              for a in oldest_first])
        self.mun_rows, self.mun_votes = {}, {}
        self.mun_rounds: dict[str, list[str]] = defaultdict(list)  # municipality code → round ids, newest first
        for a in rounds:
            rid = a.round.id
            self.mun_rows[rid] = {m["code"]: m for m in self.municipalities(a)}
            self.mun_votes[rid] = municipality_votes(a.round)
            for code in self.mun_rows[rid]:
                self.mun_rounds[code].append(rid)
        top = max(overall["counts"].values(), default=0) or 1
        appear = [{"code": c.code, "group": c.group, "n": overall["counts"][c.code],
                   "w": 100 * overall["counts"][c.code] / top}
                  for c in sorted(CHECKS, key=lambda c: -overall["counts"].get(c.code, 0)) if overall["counts"].get(c.code)]
        example = rep_rows[0] if rep_rows and rep_rows[0]["k"] >= 2 else None
        share = {a.round.id: len(a.by_station) / a.totals.stations if a.totals.stations else 0.0 for a in rounds}
        share_top = max(share.values(), default=0) or 1
        for loc in LOCALES:
            columns = [{"id": a.round.id, "title": self.round_title(a.round, loc), "national": national[a.round.id],
                        "short": self.short_title(a.round, loc)} for a in oldest_first]
            summaries = [{"id": a.round.id, "title_display": self.round_title(a.round, loc), "kind": a.round.kind,
                          "short": self.short_title(a.round, loc),
                          "date": fmt_date(self.archive.meta(a.round.id).get("date"), loc),
                          "counted": a.totals.counted, "total": a.totals.stations, "counting": a.counting,
                          "rik_time": a.round.rik_time, "fetched": a.round.fetched,
                          "flagged": len(a.by_station), "counts": dict(Counter(f.code for f in a.flags)),
                          "share": share[a.round.id], "bar": 100 * share[a.round.id] / share_top}
                         for a in rounds]
            self.write(loc, "index.html", "index.html", latest=summaries[0] if summaries else None, overall=overall,
                       checks=CHECKS, groups=GROUPS)
            self.write(loc, "elections.html", "elections.html", rounds=summaries)
            self.write_search(loc)
            self.write(loc, "guide.html", f"guide.{'en' if loc == 'en' else 'sr'}.html")
            self.write(loc, "about.html", "about.html", checks=CHECKS, groups=GROUPS)
            groups = [(k, [r for r in rep_rows if r["k"] == k]) for k in sorted({r["k"] for r in rep_rows}, reverse=True)]
            self.write(loc, "repeat.html", "repeat.html", rows=rep_rows, once=rep_once, n2=rep_n2, muns=rep_muns, groups=groups,
                       rounds=columns, same=rep_same, checks=CHECKS, group_of=group_of, example=example,
                       st_path=self.st_path)
            cols = {c["id"]: c for c in columns}
            self.place_pages(loc, cols)
            self.municipality_history_pages(loc, cols)
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
        by_station = self.flagged[rid]
        municipalities = list(self.mun_rows[rid].values())
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
        ctrl = self.ctrl_of(rid)
        ctrl_table, ctrl_readable = ctrl_rows(a.round.contestants, ctrl.values())
        common = {"rebuilt": self.archive.meta(rid).get("source") == "results_app",
                  "ctrl_readable": ctrl_readable, "a": a, "rnd": a.round, "totals": totals, "base": base, "view": view,
                  "snapshots": a.snapshots, "label": label, "rtitle": self.round_title(a.round, loc),
                  "rshort": self.short_title(a.round, loc), "st_path": self.st_path,
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
            votes = self.mun_votes[rid][m["code"]]
            mctrl, mreadable = ctrl_rows(a.round.contestants, [ctrl[s.key] for s in sts if s.key in ctrl])
            mres, top, by_st = vote_view(a.round.contestants, votes, a.totals, [s for s in sts if s.counted])
            self.write(loc, base + f"m/{m['code']}.html", "municipality.html", m=m, rows=rows, mvotes=votes,
                       mctrl=mctrl, mreadable=mreadable, mres=mres, mtop=top, mby=by_st, **common)


def vote_view(contestants, votes: list[int], totals, stations: list) -> tuple[list[dict], list[dict], list[dict]]:
    """A municipality's votes made readable: every contestant with votes, most first, with its share of valid votes
    and the national share; the three with most votes; and each station's shares for those three and the rest."""
    valid = sum(votes) or 0
    rows = []
    for i, c in enumerate(contestants):
        if votes[i]:
            share = votes[i] / valid if valid else 0
            rows.append({"index": i, "number": c.number, "label": c.label, "votes": votes[i], "share": share,
                         "national": totals.share_of_valid(i)})
    rows.sort(key=lambda r: -r["votes"])
    top_share = rows[0]["share"] if rows else 1
    for n, r in enumerate(rows):
        r["w"] = 100 * r["share"] / top_share if top_share else 0
        r["minor"] = n >= 3 and r["share"] < 0.01  # lists under 1% fold away, the top three always show
    top = rows[:3]
    by_station = []
    for s in stations:
        sv = sum(v or 0 for v in s.votes)
        cells = [((s.votes[r["index"]] or 0) / sv if sv else None, s.votes[r["index"]] or 0) for r in top]
        rest = sv - sum(v for _, v in cells)
        by_station.append({"s": s, "valid": sv, "cells": cells, "rest": (rest / sv if sv else None, rest)})
    return rows, top, by_station


def station_path(key: str) -> str:
    code, _, number = key.partition("/")
    return f"s/{code}-{re.sub(r'[^0-9A-Za-z_-]', '_', number)}.html"


def strength(code: str) -> tuple[int, int]:
    """Flags in the order the site lists them: paperwork first, then the heavier ones."""
    return GROUPS.index(BY_CODE[code].group), -BY_CODE[code].weight


def leading(votes: list) -> int | None:
    """Ballot index of the contestant with most votes (the first on the ballot when tied); None with no votes."""
    if not any(votes):
        return None
    return max(range(len(votes)), key=lambda i: votes[i] or 0)


def municipality_votes(rnd) -> dict[str, list[int]]:
    """Per municipality: each contestant's votes at the stations counted so far."""
    out: dict[str, list[int]] = {}
    n = len(rnd.contestants)
    for s in rnd.stations:
        if s.counted:
            row = out.setdefault(s.municipality_code, [0] * n)
            for i in range(n):
                row[i] += s.votes[i] or 0
        else:
            out.setdefault(s.municipality_code, [0] * n)
    return out


def display_labels(contestants) -> list[str]:
    """Contestants' labels for tight spaces: without the words that every name in the election starts with (such
    as "ИЗБОРНА ЛИСТА") and without a leading ballot number. Short names stay as they are; the full name goes in a
    tooltip."""
    labels = [c.label for c in contestants]
    split = [label.translate(LOOKALIKE).upper().split() for label in labels]
    common = 0
    if len(split) > 1:
        while all(len(w) > common + 1 and w[common] == split[0][common] for w in split):
            common += 1
    out = []
    for c, label in zip(contestants, labels):
        words = label.split()[common:]
        if len(words) > 1 and words[0].rstrip(".") == str(c.number):
            words = words[1:]
        out.append(" ".join(words) or label)
    return out


def fmt_date(iso: str | None, loc: str) -> str:
    """An election day (YYYY-MM-DD) as 25.10.2026. or 25 Oct 2026."""
    if not iso:
        return ""
    y, m, d = (int(x) for x in iso[:10].split("-"))
    return f"{d} {MONTHS_EN[m - 1]} {y}" if loc == "en" else f"{d}.{m}.{y}."


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
