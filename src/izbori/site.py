"""Static site in Serbian Latin (default), Serbian Cyrillic and English.

Serbian pages are rendered once with Cyrillic text; the Latin pages are the same HTML run through the
transliterator. Links to RIK documents are percent-encoded first, so transliteration never touches them."""

from __future__ import annotations

import re
import json
import bisect
import shutil
import hashlib
import platform
from collections import Counter, defaultdict
from importlib.metadata import version
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
from izbori.i18n import (LANG_ATTR, LOCALES, PREFIX, S, check_name, check_rule, fmt_date, fmt_int, fmt_num, fmt_pct,
                         fmt_time, keep, kind_name, latin_page, strip_keep, t)
from izbori import documents, narrative
from izbori.places import RULES_FILE, Place, contradicts, follow
from izbori.report import Analysis, analyze, links
from izbori.translit import latin

HERE = Path(__file__).parent
LANG_LABELS = {"lat": "Latinica", "cyr": keep("Ћирилица"), "en": "English"}
SERIES = 8  # categorical colour slots in site.css
LOOKALIKE = str.maketrans("AaEeOoPpCcXxKkMHTBy", "АаЕеОоРрСсХхКкМНТВу")  # Latin letters RIK sometimes types for Cyrillic


class Site:
    """The whole site. With incremental=True the previous build in `out` is kept, and a page is rendered again only
    when what it shows has changed: each page's inputs are fingerprinted and the fingerprints saved next to the
    output (`<out>.state.json`). Changed code, templates or packages rebuild every page; files no page produced any
    more are removed, so the result is the same as a full build."""

    def __init__(self, archive: Archive, out: Path, notes_dir: Path | None, site_url: str = SITE_URL,
                 incremental: bool = False):
        self.archive = archive
        self.out = Path(out)
        self.notes_dir = notes_dir
        self.site_url = site_url
        self.incremental = incremental
        self.state_path = self.out.parent / (self.out.name + ".state.json")
        self.version = code_version()
        self.previous: dict[str, str] = {}
        self.state: dict[str, str] = {}
        self.produced: set[str] = set()
        self.kept = self.rendered = 0
        self.env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(),
                               trim_blocks=True, lstrip_blocks=True)
        self.env.filters["url"] = safe_url
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
            "time": lambda v: fmt_time(v, loc), "date": lambda v: fmt_date(v, loc), "name": name,
            "kind_name": lambda k: kind_name(k, loc),
            "check_name": lambda c: check_name(c, loc), "check_rule": lambda c: check_rule(c, loc, RULES),
            "repo_url": REPO_URL, "rik_url": RIK_PUBLIC, "feed_href": root + ("feed.en.xml" if loc == "en"
                                                                              else "feed.sr.xml"),
            **extra,
        }

    def write(self, loc: str, page: str, template: str, **extra) -> None:
        html = self.env.get_template(template).render(**self.context(loc, page, **extra))
        html = latin_page(html) if loc == "lat" else strip_keep(html)
        self.put(PREFIX[loc] + page, html)

    def put(self, rel: str, text: str) -> None:
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.produced.add(rel)
        self.rendered += 1

    def keep(self, loc: str, page: str, inputs: str) -> bool:
        """Record what the page is made from; True when the previous build already has it from the same inputs, so
        it needn't be rendered again."""
        rel = PREFIX[loc] + page
        fp = hashlib.blake2b(f"{self.version}|{loc}|{inputs}".encode(), digest_size=16).hexdigest()
        self.state[rel] = fp
        if self.previous.get(rel) == fp and (self.out / rel).exists():
            self.produced.add(rel)
            self.kept += 1
            return True
        return False

    # --- view models -------------------------------------------------------------------------
    def st_path(self, rid: str, key: str) -> str:
        """The page of the place a round's station belongs to: that place in every election in the archive."""
        p = self.places.of(rid, key)
        return f"s/{p.id}.html" if p else ""

    def ctrl_of(self, rid: str) -> dict:
        if rid not in self.ctrl_cache:
            store = boards.load_store(self.archive.dir(rid))
            cov = boards.coverage(store)
            names = {s.key: s.name for s in self.analyses[rid].round.stations} if rid in self.analyses else {}
            for key, c in cov.items():  # an address naming another building than the results is not shown
                if c.get("address") and contradicts(names.get(key, ""), c["address"]):
                    c["address"] = ""
            self.ctrl_cache[rid] = cov
            self.board_docs_cache[rid] = boards.station_docs(store)
        return self.ctrl_cache[rid]

    def board_docs_of(self, rid: str) -> dict:
        """Per station key, its decisions on the polling board (appointments and changes), to link."""
        self.ctrl_of(rid)
        return self.board_docs_cache[rid]

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
            if self.keep(loc, f"s/{p.id}.html", self.place_inputs(p, loc)):
                continue
            rows, codes, story = [], set(), []
            for i, rid in enumerate(p.rounds):
                a, s = self.analyses[rid], p.stations[rid]
                flags = self.flagged[rid].get(s.key, [])
                codes.update(f.code for f in flags)
                ctrl = self.ctrl_of(rid)
                older = p.stations[p.rounds[i + 1]] if i + 1 < len(p.rounds) else None
                rows.append({"rid": rid, "short": cols[rid]["short"], "date": fmt_date(self.dates[rid], loc), "s": s,
                             "how": p.how[rid] if older is not None and older.number != s.number else "",
                             "address": p.addresses.get(rid, ""), "flags": self.flag_view(a, flags, loc),
                             "notes": a.notes.get(s.key, []), "ctrl": ctrl.get(s.key), "ctrl_known": bool(ctrl),
                             "docs": a.documents.get(s.key, []), "review": a.reviews.get(s.key),
                             "board_docs": self.board_docs_of(rid).get(s.key, []),
                             "n_lists": len(a.round.contestants),
                             "top": self.top_three(rid, s.votes) if s.counted else []})
                story.append(self.place_election(rid, s, flags, cols[rid]["short"]))
            hints = sorted(codes, key=strength)
            self.write(loc, f"s/{p.id}.html", "station.html", p=p, s=p.newest, rows=rows, address=p.address,
                       hints=hints, group_of=group_of,
                       analysis=narrative.place(story, [cols[r]["short"] for r in self.mun_rounds[p.code]
                                                        if r not in p.stations], loc),
                       charts=self.trends(p.rounds, story, "mun", loc))

    def place_inputs(self, p: Place, loc: str) -> str:
        """Everything a place's page is made from, as text to fingerprint."""
        parts = [p.id, p.rounds, sorted(p.how.items()), sorted(p.addresses.items()),
                 [(r, self.shorts[loc][r], self.dates[r]) for r in self.mun_rounds[p.code]]]
        for rid in p.rounds:
            s = p.stations[rid]
            parts.append((rid, self.round_inputs[rid], s, self.flagged[rid].get(s.key), self.analyses[rid].notes.get(s.key),
                          self.ctrl_of(rid).get(s.key), self.mun_rows[rid][s.municipality_code],
                          self.mun_votes[rid][s.municipality_code],
                          self.peers[rid]["st"].get(s.municipality_code, {}).get("digest"),
                          self.analyses[rid].documents.get(s.key), self.analyses[rid].reviews.get(s.key)))
        return repr(parts)

    def round_key(self, rid: str) -> str:
        """What a round's pages are made from: the archived files of this round and of the earlier ones (flags compare
        with them), and the pages its stations link to (place pages are named after the newest election)."""
        if rid not in self.round_keys:
            files = [self.archive.root / RULES_FILE]  # manual corrections change which stations are compared
            for r in self.rids[: self.rids.index(rid) + 1]:
                d = self.archive.dir(r)
                files += [d / n for n in ("results.csv", "meta.json", "changes.jsonl", "snapshots.jsonl", "state.json",
                                          "flags_seen.json", "first_seen.json", "boards.json", "documents.json",
                                          "observer_reviews.csv")]
                if self.notes_dir:
                    files.append(Path(self.notes_dir) / f"{r}.csv")
            links = hashlib.sha256("|".join(self.st_path(rid, s.key) for s in self.analyses[rid].round.stations).encode())
            self.round_keys[rid] = file_digest(*files) + links.hexdigest()
        return self.round_keys[rid]

    def trends(self, rids: list[str], rows: list[narrative.Election], ref: str, loc: str) -> list[dict]:
        """The charts across elections for a page: turnout and the share of invalid ballots, each drawn when it is
        known in at least two elections. rids and rows: newest first; ref: "mun" or "all"."""
        points = []
        for rid, e in reversed(list(zip(rids, rows))):
            kind = self.analyses[rid].round.kind
            points.append({"abbr": t(f"abbr_{kind}", loc) if f"abbr_{kind}" in S else "", "title": self.shorts[loc][rid],
                           "year": (self.dates[rid] or "")[:4], "turnout": e.turnout, "ref_turnout": e.ref_turnout,
                           "invalid": e.invalid, "ref_invalid": e.ref_invalid})
        charts = []
        for key, title, zero in (("turnout", t("turnout", loc), False), ("invalid", t("trend_invalid", loc), True)):
            if sum(1 for p in points if p[key] is not None) >= 2:
                pts = [{**p, "v": p[key], "r": p[f"ref_{key}"]} for p in points]
                charts.append({"title": title, "svg": svg.trend(pts, title, t(f"an_label_{ref}", loc), loc, zero=zero)})
        return charts

    def place_election(self, rid: str, s, flags: list, short: str) -> narrative.Election:
        """One election at a polling place, next to its municipality in the same election."""
        m, mv = self.mun_rows[rid][s.municipality_code], self.mun_votes[rid][s.municipality_code]
        e = narrative.Election(short=short, number=s.number, name=s.name,
                               flags=sorted(dict.fromkeys(f.code for f in flags), key=strength),
                               ref_turnout=m["turnout"], ref_invalid=m["invalid"])
        if self.docs_known[rid]:
            e.observers = any(d.kind == "observers" for d in self.analyses[rid].documents.get(s.key, []))
        if s.counted:
            e.registered, e.turnout, e.invalid = s.registered, s.turnout, s.invalid_share
            st = self.peers[rid]["st"].get(s.municipality_code, {})
            e.rank_invalid = rank_of(e.invalid, st.get("invalid"))
            e.rank_turnout = rank_of(e.turnout, st.get("turnout"))
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
        if self.docs_known[rid]:
            e.observed = self.observed[rid][code]
        if m["kind"] == "domestic":
            e.rank_invalid = rank_of(m["invalid"], self.peers[rid]["mun"]["invalid"])
            e.rank_turnout = rank_of(m["turnout"], self.peers[rid]["mun"]["turnout"])
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
            inputs = repr([code, rids, [(rid, self.round_inputs[rid], self.shorts[loc][rid], self.mun_rows[rid][code],
                                         self.mun_votes[rid][code], self.analyses[rid].totals, len(self.flagged[rid]),
                                         self.peers[rid]["mun"]["digest"], self.docs_known[rid],
                                         self.observed[rid][code]) for rid in rids],
                           [(p.id, p.rounds, p.newest.number, p.newest.name, p.former_numbers, self.flagged_in(p))
                            for p in by_code[code]], [self.shorts[loc][r] for r in newest_first if r not in rids]])
            if self.keep(loc, f"m/{code}.html", inputs):
                continue
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
            elections = [self.municipality_election(rid, code, cols[rid]["short"]) for rid in rids]
            analysis = narrative.municipality(elections, [cols[r]["short"] for r in newest_first if r not in rids],
                                              repeat, network, loc)
            self.write(loc, f"m/{code}.html", "municipality_history.html", code=code, mname=newest["name"],
                       feed_href=f"{'../' * (PREFIX[loc] + 'm/').count('/')}feed/{code}.{'en' if loc == 'en' else 'sr'}.xml",
                       district=newest["district"] if newest["kind"] == "domestic" else "", rows=rows, places=places,
                       analysis=analysis, charts=self.trends(rids, elections, "all", loc))

    def write_api(self) -> None:
        """The data behind the pages across elections as JSON, for anyone who wants it without parsing HTML:
        api/index.json (elections, municipalities, places), api/m/<code>.json and api/s/<place>.json. Names are as
        RIK publishes them; shares are fractions; votes list each contestant with any vote, by ballot number."""
        rounds = []
        for rid in reversed(self.rids):
            meta, rnd = self.archive.meta(rid), self.analyses[rid].round
            rounds.append({"id": rid, "kind": rnd.kind, "date": self.dates[rid], "title": rnd.title,
                           "title_en": meta.get("title_en", ""),
                           "contestants": [{"number": c.number, "name": c.name, "short": c.short} for c in rnd.contestants]})
        names = {code: self.mun_rows[rids[0]][code]["name"] for code, rids in self.mun_rounds.items()}
        index = {"rounds": rounds,
                 "municipalities": [{"code": c, "name": names[c], "rounds": self.mun_rounds[c]} for c in sorted(names)],
                 "places": [{"id": p.id, "municipality": p.code, "number": p.newest.number, "name": p.newest.name}
                            for p in self.places.places]}
        self.put("api/index.json", dump(index))
        by_code: dict[str, list[str]] = defaultdict(list)
        for p in self.places.places:
            by_code[p.code].append(p.id)
            if not self.keep("lat", f"api/s/{p.id}.json", self.place_inputs(p, "lat")):
                self.put(f"api/s/{p.id}.json", dump(self.place_json(p)))
        for code, rids in self.mun_rounds.items():
            elections = []
            for rid in rids:
                m, mv = self.mun_rows[rid][code], self.mun_votes[rid][code]
                elections.append({"round": rid, "stations": m["stations"], "counted": m["counted"],
                                  "registered": m["registered"], "voted": m["voted"], "turnout": m["turnout"],
                                  "invalid_share": m["invalid"], "flagged": m["flagged"],
                                  "votes": votes_json(self.analyses[rid].round.contestants, mv)})
            data = {"code": code, "name": names[code], "elections": elections, "places": by_code[code]}
            text = dump(data)
            if not self.keep("lat", f"api/m/{code}.json", text):
                self.put(f"api/m/{code}.json", text)

    def place_json(self, p: Place) -> dict:
        elections = []
        for rid in p.rounds:
            s, a = p.stations[rid], self.analyses[rid]
            ctrl = self.ctrl_of(rid).get(s.key)
            elections.append({
                "round": rid, "number": s.number, "name": s.name, "joined_by": p.how[rid] or None,
                "address": p.addresses.get(rid) or None, "registered": s.registered, "voted": s.voted,
                "ballots": s.ballots, "valid": s.valid, "invalid": s.invalid, "turnout": s.turnout,
                "invalid_share": s.invalid_share, "votes": votes_json(a.round.contestants, s.votes),
                "flags": [{"code": f.code, "data": f.data} for f in self.flagged[rid].get(s.key, [])],
                "minutes": [d.url for d in a.documents.get(s.key, []) if d.kind == "minutes"],
                "corrections": [d.url for d in a.documents.get(s.key, []) if d.kind == "correction"],
                "documents": [{"kind": d.kind, "repeat": d.repeat, "label": d.label or None, "url": d.url,
                               "uploaded": d.uploaded or None}
                              for d in a.documents.get(s.key, []) + self.board_docs_of(rid).get(s.key, [])],
                "controllers": ctrl.get("lists") if ctrl else None,
                "notes": [{"date": n.date, "outlet": n.outlet, "url": n.url, "archive_url": n.archive_url,
                           "summary_sr": n.summary_sr, "summary_en": n.summary_en} for n in a.notes.get(s.key, [])]})
        return {"id": p.id, "municipality": {"code": p.code, "name": p.newest.municipality},
                "number": p.newest.number, "name": p.newest.name, "address": p.address or None, "elections": elections}

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
        self.put(PREFIX[loc] + "search.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))

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
        if self.incremental and self.state_path.exists() and self.out.exists():
            saved = json.loads(self.state_path.read_text(encoding="utf-8"))
            if saved.get("version") == self.version:
                self.previous = saved.get("pages", {})
        elif self.out.exists():
            shutil.rmtree(self.out)
        (self.out / "static").mkdir(parents=True, exist_ok=True)
        shutil.copytree(HERE / "static", self.out / "static", dirs_exist_ok=True)
        self.produced.update(str(f.relative_to(self.out)) for f in (self.out / "static").rglob("*") if f.is_file()
                             and (HERE / f.relative_to(self.out)).exists())
        self.put(".nojekyll", "")
        self.cache: dict = {}
        self.ctrl_cache: dict = {}
        self.board_docs_cache: dict = {}
        rids = self.archive.round_ids()
        for rid in rids:
            self.analyses[rid] = analyze(self.archive, rid, self.notes_dir, self.cache)
        rounds = [self.analyses[r] for r in reversed(rids)]
        oldest_first = [self.analyses[r] for r in rids]
        # the same polling place across elections (address, name, number, manual corrections): the checks used
        # these links too, and the history table, the search and the pages across elections all follow them
        self.places = links(self.archive, rids[-1], self.cache) if rids else follow([])
        rep_rows, rep_once = repeat.stations(oldest_first, self.places)
        rep_muns, national = repeat.municipalities(oldest_first)
        rep_same = repeat.same_counts(rep_rows)
        rep_n2 = sum(1 for r in rep_rows if r["k"] >= 2)
        by_code = defaultdict(set)
        for a in oldest_first:
            for key, flags in a.by_station.items():
                for f in flags:
                    by_code[f.code].add(self.places.of(a.round.id, key).id)
        overall = {"flagged": len(rep_rows), "total": len(self.places.places), "repeated": rep_n2,
                   "counts": {code: len(ids) for code, ids in by_code.items()}}
        group_of = {c.code: c.group for c in CHECKS}
        # the same polling place and municipality across elections, for the search and the pages across elections
        self.rids = rids
        self.dates = {rid: self.archive.meta(rid).get("date") for rid in rids}
        self.flagged = {a.round.id: a.by_station for a in oldest_first}
        self.labels = {a.round.id: display_labels(a.round.contestants) for a in oldest_first}
        self.shorts = {loc: {a.round.id: self.short_title(a.round, loc) for a in oldest_first} for loc in LOCALES}
        self.round_inputs = {a.round.id: repr((a.round.kind, self.dates[a.round.id], self.labels[a.round.id],
                                               [(c.number, c.name, c.short) for c in a.round.contestants]))
                             for a in oldest_first}
        self.round_keys: dict[str, str] = {}
        # rounds whose documents are known: RIK's register was read, or the results file lists observers' records
        self.docs_known = {a.round.id: documents.path(self.archive.dir(a.round.id)).exists()
                           or any(d.kind == "observers" for docs in a.documents.values() for d in docs)
                           for a in oldest_first}
        self.observed = {a.round.id: Counter(s.municipality_code for s in a.round.stations
                                             if any(d.kind == "observers" for d in a.documents.get(s.key, [])))
                         for a in oldest_first}  # municipality code → its stations with an observers' record
        self.mun_rows, self.mun_votes = {}, {}
        self.mun_rounds: dict[str, list[str]] = defaultdict(list)  # municipality code → round ids, newest first
        self.peers: dict[str, dict] = {}  # round id → sorted values to rank stations and municipalities by
        for a in rounds:
            rid = a.round.id
            self.mun_rows[rid] = {m["code"]: m for m in self.municipalities(a)}
            self.mun_votes[rid] = municipality_votes(a.round)
            for code in self.mun_rows[rid]:
                self.mun_rounds[code].append(rid)
            self.peers[rid] = peer_values(a.round, self.mun_rows[rid])
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
        self.write_api()
        # GitHub Pages serves this file for a missing page at any depth, so its links are absolute.
        self.write("lat", "404.html", "404.html", root=self.site_url,
                   link=lambda target: self.site_url + target)
        self.put("feed.sr.xml", feed.build(self.archive.root, self.archive, "lat", self.site_url))
        self.put("feed.en.xml", feed.build(self.archive.root, self.archive, "en", self.site_url))
        entries = feed.load_entries(self.archive.root)
        for code, rids in self.mun_rounds.items():  # one feed per municipality, for observers who follow one place
            name = self.mun_rows[rids[0]][code]["name"]
            for loc, lang in (("lat", "sr"), ("en", "en")):
                self.put(f"feed/{code}.{lang}.xml", feed.build(self.archive.root, self.archive, loc, self.site_url,
                                                               municipality=(code, name), entries=entries))
        self.finish()
        return self.out

    def finish(self) -> None:
        """Remove what no page produced any more (pages of places that no longer exist, old static files) and save
        the fingerprints for the next incremental build."""
        for f in sorted(self.out.rglob("*"), reverse=True):
            rel = str(f.relative_to(self.out))
            if f.is_file() and rel not in self.produced:
                f.unlink()
            elif f.is_dir() and not any(f.iterdir()):
                f.rmdir()
        self.state_path.write_text(json.dumps({"version": self.version, "pages": self.state}, sort_keys=True),
                                   encoding="utf-8")

    def round_pages(self, a: Analysis, loc: str) -> None:
        rid = a.round.id
        base = f"r/{rid}/"
        pages = [base + "index.html", base + "check.html", base + "changes.html"] + [
            base + f"m/{code}.html" for code in self.mun_rows[rid]]
        if all([self.keep(loc, page, self.round_key(rid)) for page in pages]):  # a list: every page is recorded
            return
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
                "seen": min(seen) if seen else None, "notes": a.notes.get(key, []), "docs": a.documents.get(key, []),
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
                     "notes": a.notes.get(s.key, []), "docs": a.documents.get(s.key, [])} for s in sts]
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


def strength(code: str) -> tuple[int, int, str]:
    """Flags in the order the site lists them: paperwork first, then the heavier ones (by name when equal, so every
    build lists them alike)."""
    return GROUPS.index(BY_CODE[code].group), -BY_CODE[code].weight, code


def dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def votes_json(contestants, votes: list) -> list[list[int]]:
    """[ballot number, votes] for each contestant with any vote."""
    return [[c.number, votes[i]] for i, c in enumerate(contestants) if i < len(votes) and votes[i]]


PEERS_MIN = 5  # fewer peers than this, and a rank says little


def peer_values(rnd, municipalities: dict[str, dict]) -> dict:
    """Sorted invalid shares and turnouts to rank by: each municipality's counted stations, and the municipalities in
    Serbia (not abroad or prisons). A digest of each set goes into the pages' fingerprints."""
    by_code: dict[str, list] = defaultdict(list)
    for s in rnd.stations:
        if s.counted:
            by_code[s.municipality_code].append(s)

    def entry(invalid: list, turnout: list) -> dict:
        out = {"invalid": sorted(v for v in invalid if v is not None), "turnout": sorted(v for v in turnout if v is not None)}
        out["digest"] = hashlib.blake2b(repr(out).encode(), digest_size=8).hexdigest()
        return out
    domestic = [m for m in municipalities.values() if m["kind"] == "domestic"]
    return {"st": {code: entry([s.invalid_share for s in sts], [s.turnout for s in sts]) for code, sts in by_code.items()},
            "mun": entry([m["invalid"] for m in domestic], [m["turnout"] for m in domestic])}


def rank_of(value: float | None, values: list | None) -> tuple[int, int] | None:
    """Rank from the highest (ties share a rank) and the number ranked; None with too few values."""
    if value is None or not values or len(values) < PEERS_MIN:
        return None
    return 1 + len(values) - bisect.bisect_right(values, value), len(values)


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


def build(archive: Archive, out: Path, notes_dir: Path | None, site_url: str = SITE_URL,
          incremental: bool = False) -> Path:
    return Site(archive, out, notes_dir, site_url, incremental).build()


def code_version() -> str:
    """Everything that shapes the pages besides the data: this package's code, templates and static files, and the
    versions of the packages that render them. A change rebuilds every page."""
    h = hashlib.sha256()
    for f in sorted(p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        h.update(str(f.relative_to(HERE)).encode())
        h.update(f.read_bytes())
    for package in ("jinja2", "markupsafe"):
        h.update(f"{package}={version(package)}".encode())
    h.update(platform.python_version().encode())
    return h.hexdigest()[:16]


def file_digest(*paths: Path) -> str:
    """One digest for the content of these files; a missing file counts as empty."""
    h = hashlib.sha256()
    for path in paths:
        h.update(str(path.name).encode())
        h.update(path.read_bytes() if path.exists() else b"")
    return h.hexdigest()
