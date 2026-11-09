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
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from izbori import boards, feed, maps, repeat, stats, svg
from izbori.checks import BY_CODE, CHECKS, GROUPS, RULES
from izbori.config import REPO_URL, RIK_PUBLIC, SITE_URL
from izbori.contests import Presidential, Proportional, contest_rules
from izbori.describe import describe, field_label
from izbori.history import Archive
from izbori.links import safe_url
from izbori.model import ABROAD, PRISONS, last_url
from izbori.i18n import (BELGRADE, BUILT, LANG_ATTR, LOCALES, PREFIX, S, check_name, check_rule, collate, fmt_date, fmt_int,
                         fmt_num, fmt_pct, fmt_time, keep, kind_name, latin_page, strip_keep, t)
from izbori import (bysettlement, cities, commission, coordinator, documents, geo, highlights, narrative, publishing, schedule,
                    settlements)
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
                  "current": other == loc, "lang": LANG_ATTR[other]} for other in BUILT]
        return {
            "loc": loc, "lang": LANG_ATTR[loc], "root": root, "link": link, "langs": langs, "page": page,
            "site_host": self.site_url.split("://", 1)[-1].rstrip("/"),
            "mun_href": lambda code: link(self.slugs[code] + "/") if code in getattr(self, "slugs", {}) else link(f"m/{code}.html"),
            "city_href": lambda slug: link(slug + "/"),
            # the page's address as printed on a shared image: izbornipodaci.rs/pirot
            "mun_url": lambda code: (self.site_url.split("://", 1)[-1].rstrip("/") + "/" + PREFIX[loc]
                                     + self.slugs.get(code, f"m/{code}.html") if hasattr(self, "slugs") else ""),
            "t": lambda key, **kw: t(key, loc, **kw), "i": lambda n: fmt_int(n, loc),
            "pct": lambda x, d=1: fmt_pct(x, loc, d), "num": lambda x, d=1: fmt_num(x, loc, d),
            "pval": lambda x: "< " + fmt_num(0.001, loc, 3) if x < 0.001 else fmt_num(x, loc, 3),
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
        self.put(PREFIX[loc] + page, compact(html))

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
        return self.place_path(p) if p else ""

    def place_path(self, p) -> str:
        """A polling place's address: its municipality's name and its newest number, /novi-sad/140/ (the election's
        id after the number where another place in the municipality has the same newest number). The old
        s/<place>.html is a one-line page that leads here."""
        return f"{self.slugs[p.code]}/{p.id[len(p.code) + 1:]}/" if getattr(self, "slugs", None) else f"s/{p.id}.html"

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

    def commission_of(self, rid: str) -> dict:
        """Per municipality code, its electoral commission's documents by kind."""
        if rid not in self.commission_cache:
            self.commission_cache[rid] = commission.by_municipality(commission.load_store(self.archive.dir(rid)))
        return self.commission_cache[rid]

    @property
    def figures(self) -> dict:
        """Each census settlement's figures (settlements.load_figures), read once."""
        if self.figures_cache is None:
            self.figures_cache = settlements.load_figures(self.archive.root)
        return self.figures_cache

    def settlements_of(self, rid: str) -> dict[str, dict]:
        """The round's stations' settlements (settlements.json): station key → census municipality, settlement, rule."""
        return settlements.load_store(self.archive.dir(rid)).get("stations", {})

    def by_settlement_of(self, rid: str) -> dict:
        """Results and controllers by kind of settlement (bysettlement.py), with the contestants' display labels."""
        if rid not in self.settlement_cache:
            a = self.analyses[rid]
            result = bysettlement.analyse(a.round.stations, a.round.contestants, self.settlements_of(rid),
                                          self.figures, self.ctrl_of(rid))
            for row in result["rows"]:
                row["label"] = self.labels[rid][row["index"]]
            self.settlement_cache[rid] = result
        return self.settlement_cache[rid]

    def publishing_of(self, rid: str) -> tuple[list, dict]:
        """Per municipality in Serbia, what reached RIK's registers for its stations and from its commission, and
        when (publishing.py); with the whole country's line."""
        if rid not in self.publishing_cache:
            a = self.analyses[rid]
            by_code: dict[str, list] = defaultdict(list)
            for s in a.round.stations:
                by_code[s.municipality_code].append(s)
            close = publishing.closing(self.dates[rid] or "")
            board = self.board_docs_of(rid)
            cdocs = city = None
            city_n = unplaced = 0
            if commission.path(self.archive.dir(rid)).exists():
                cdocs = {code: sum(len(g["docs"]) for g in groups) for code, groups in self.commission_of(rid).items()}
                by_city, city_n, unplaced = self.city_docs_of(rid)
                city = {code: v["n"] for code, v in by_city.items()}
            changed = {key for key, flags in self.flagged[rid].items() if any(f.check.group == "change" for f in flags)}
            rows = publishing.rows(list(self.mun_rows[rid].values()), by_code, a.documents, close, board or None, cdocs,
                                   changed, city)
            self.publishing_cache[rid] = (rows, publishing.summary(rows, a.documents, a.round.stations, close,
                                                                   unplaced, city_n))
        return self.publishing_cache[rid]

    def city_docs_of(self, rid: str) -> tuple[dict, int, int]:
        """Per city municipality, its city's commission's documents in this round (commission.city_parts): those RIK
        lists under a city the results don't have (Niš), or the city's own (Požarevac's for Kostolac); then how many
        documents RIK lists under such cities, each once, and how many under a name no municipality takes."""
        if rid not in self.city_cache:
            store = commission.load_store(self.archive.dir(rid))
            cities, own = commission.by_city(store), self.commission_of(rid)
            out, used = {}, set()
            for code in self.mun_rows[rid]:
                kind, key = self.city_parts.get(code, ("", ""))
                if kind == "name" and key in cities:
                    out[code] = {"name": cities[key]["name"], "groups": cities[key]["groups"]}
                    used.add(key)
                elif kind == "code" and own.get(key):
                    newest = self.mun_rows[self.mun_rounds[key][0]][key]["name"] if self.mun_rounds.get(key) else key
                    out[code] = {"name": self.mun_rows[rid].get(key, {}).get("name") or newest, "groups": own[key]}
            for v in out.values():
                v["name"] = re.sub(r"^Град\s+", "", v["name"])
                v["n"] = commission.count(v["groups"])
            unplaced = sum(1 for d in store.get("docs", {}).values() if d.get("m") not in self.mun_rows[rid]
                           and not (not d.get("m") and d.get("n") and boards.municipality_key(d["n"]) in used))
            self.city_cache[rid] = (out, sum(commission.count(cities[k]["groups"]) for k in used), unplaced)
        return self.city_cache[rid]

    def board_docs_of(self, rid: str) -> dict:
        """Per station key, its decisions on the polling board (appointments and changes), to link."""
        self.ctrl_of(rid)
        return self.board_docs_cache[rid]

    def linked_docs(self, rid: str) -> int:
        """How many of RIK's documents a round's pages link to: the stations' documents (minutes, observers' records,
        remarks, rulings), the decisions on polling boards and the electoral commissions' documents."""
        return (sum(len(d) for d in self.analyses[rid].documents.values())
                + sum(len(d) for d in self.board_docs_of(rid).values())
                + sum(len(g["docs"]) for groups in self.commission_of(rid).values() for g in groups)
                + self.city_docs_of(rid)[1])

    def home_data(self, latest: Analysis | None) -> dict:
        """What the home page shows besides the cards: the archive in numbers, whether the latest election has
        controllers to show, and the next election a maintainer entered, with the deadlines still ahead."""
        years = sorted(d[:4] for d in self.dates.values() if d)
        home = {"rounds": len(self.rids), "first": years[0] if years else "", "last": years[-1] if years else "",
                "places": len(self.places.places), "docs": sum(self.linked_docs(rid) for rid in self.rids),
                "ctrl": bool(latest and self.ctrl_of(latest.round.id)), "next": None,
                "census": bool(latest and self.by_settlement_of(latest.round.id)["used"]),
                "stations": latest.totals.stations if latest else 0, "examples": [], "municipalities": []}
        if latest:
            rid = latest.round.id
            muns = [m for m in self.mun_rows[rid].values() if m["kind"] == "domestic"]
            home["municipalities"] = [{"name": m["name"], "href": f"{self.slugs[m['code']]}/"}
                                      for m in sorted(muns, key=lambda m: collate(m["name"], "cyr"))]
            # what to try in the search: the largest municipality, a station by name, a station by number
            biggest = max(muns, key=lambda m: m["stations"], default=None)
            named = next((s for s in latest.round.stations if s.kind == "domestic" and s.name
                          and self.st_path(rid, s.key) and 6 <= len(s.name) <= 24), None)
            numbered = next((s for s in reversed(latest.round.stations) if s.kind == "domestic"
                             and self.st_path(rid, s.key) and s.number.isdigit() and int(s.number) > 20), None)
            home["examples"] = [e for e in (
                biggest and {"label": biggest["name"], "href": f"{self.slugs[biggest['code']]}/"},
                named and {"label": named.name, "href": self.st_path(rid, named.key)},
                numbered and {"label": f"{numbered.municipality} {numbered.number}",
                              "href": self.st_path(rid, numbered.key)}) if e]
        today = datetime.now(BELGRADE).date()
        ahead = schedule.upcoming(self.archive.root, today)
        if ahead:
            day = ahead[0]["day"]
            home["next"] = {"day": day.isoformat(), "kinds": list(dict.fromkeys(r["kind"] for r in ahead)),
                            "notes": [r["note"] for r in ahead if r["note"]],
                            "deadlines": [(key, d.isoformat()) for key, d in schedule.deadlines(day, today)]}
        return home

    def highlights_of(self, rid: str) -> dict:
        """The home page's four cards about the latest election (highlights.py)."""
        muns = list(self.mun_rows[rid].values())
        names = {m["code"]: m["name"] for m in muns}
        a = self.analyses[rid]
        return {"gap": highlights.gap(self.by_settlement_of(rid)["rows"]), "flagged": highlights.flagged(muns),
                "repeated": highlights.repeated(self.places.places, self.flagged, names),
                "top": highlights.top(a.round.contestants, self.labels[rid], muns, self.mun_votes[rid])}

    def explore_meta(self, loc: str) -> dict:
        """What the Explore page's script needs besides the stations' files: the elections, newest first, with their
        lists in ballot order and whether controllers and observers' records are known; the municipalities' names;
        and the page's strings, all in the page's language. The stations themselves are in api/r/<id>/stations.json."""
        name = latin if loc == "en" else (lambda x: x)  # the Latin page is transliterated whole
        rounds = [{"id": rid, "short": self.shorts[loc][rid], "date": self.dates[rid] or "",
                   "kind": self.analyses[rid].round.kind, "ctrl": bool(self.ctrl_of(rid)), "obs": self.docs_known[rid],
                   "census": bool(self.by_settlement_of(rid)["used"]),
                   "lists": [{"n": c.number, "name": name(c.short or c.name)}
                             for c in self.analyses[rid].round.contestants]}
                  for rid in reversed(self.rids)]
        muns = {code: name(self.mun_rows[rids[0]][code]["name"]) for code, rids in self.mun_rounds.items()}  # newest
        strings = {k: t(k, loc) for k in S if k.startswith(("ex_", "m_", "view_", "level_", "preset_"))}
        strings.update({f"group_{g}": t(f"group_{g}", loc) for g in GROUPS})
        # the settlements' classes, named as on the round's page by kind of settlement
        strings.update({f"ex_{k}": t(k, loc) for k in S if k.startswith(("sx_type_", "sx_size_", "sx_change_"))})
        return {"loc": loc, "rounds": rounds, "muns": muns, "slugs": self.slugs, "groups": GROUPS, "t": strings,
                "abroad": ABROAD.strip("/"), "prisons": PRISONS.strip("/"), "classes": bysettlement.CLASSES}

    def municipality_index(self, loc: str) -> list[dict]:
        """Every municipality in the archive, in alphabetical order: how many elections, its polling stations at the
        latest one, and the newest election whose electoral commission's documents are known, with how many."""
        rows = []
        for code, rids in self.mun_rounds.items():
            newest = self.mun_rows[rids[0]][code]
            def docs_in(r: str) -> int:  # its commission's, or its city's commission's, documents
                return (commission.count(self.commission_of(r).get(code, []))
                        + self.city_docs_of(r)[0].get(code, {}).get("n", 0))
            crid = next((r for r in rids if docs_in(r)), None)
            last = self.rids[-1]  # the archive's newest election: named only where a row refers to another one
            rows.append({"code": code, "name": newest["name"], "n": len(rids), "stations": newest["stations"], "rid": rids[0],
                         "latest": self.shorts[loc][rids[0]] if rids[0] != last else "", "crid": crid,
                         "cdocs": docs_in(crid) if crid else 0,
                         "cshort": self.shorts[loc][crid] if crid and crid != last else ""})
        rows.sort(key=lambda r: collate(latin(r["name"]) if loc == "en" else r["name"], loc))
        return rows

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

    def place_results(self, rid: str, s) -> tuple[list[dict], int, int]:
        """A station's result as the page shows it: every contestant with at least 1% of its valid votes (and at
        least the first three), most votes first, each with its share here, in the municipality and in the whole
        election; then how many contestants are left and the votes they got between them."""
        total = sum(v or 0 for v in s.votes)
        if not total:
            return [], len(s.votes), 0
        a, mv, labels = self.analyses[rid], self.mun_votes[rid][s.municipality_code], self.labels[rid]
        mun_total = sum(mv)
        order = sorted(range(len(s.votes)), key=lambda i: (-(s.votes[i] or 0), i))
        shown = [i for k, i in enumerate(order) if (s.votes[i] or 0) and ((s.votes[i] or 0) / total >= 0.01 or k < 3)]
        rows = [{"number": a.round.contestants[i].number, "label": narrative.short_label(labels[i]),
                 "full": a.round.contestants[i].name,
                 "votes": s.votes[i] or 0, "share": (s.votes[i] or 0) / total,
                 "mun": mv[i] / mun_total if mun_total else None, "country": a.totals.share_of_valid(i)}
                for i in shown]
        rest = [i for i in order if i not in set(shown)]
        return rows, len(rest), sum(s.votes[i] or 0 for i in rest)

    def place_pages(self, loc: str, cols: dict) -> None:
        """One page for every polling place: a few sentences about it, then one row per election it took part in,
        newest first, every election alike, each linking to the station's row in that election."""
        group_of = {c.code: c.group for c in CHECKS}
        for p in self.places.places:
            path = self.place_path(p)
            self.redirect(loc, f"s/{p.id}.html", "../" + path)
            if self.keep(loc, path + "index.html", self.place_inputs(p, loc)):
                continue
            rows, codes, story = [], set(), []
            for i, rid in enumerate(p.rounds):
                a, s = self.analyses[rid], p.stations[rid]
                flags = self.flagged[rid].get(s.key, [])
                codes.update(f.code for f in flags)
                ctrl = self.ctrl_of(rid)
                older = p.stations[p.rounds[i + 1]] if i + 1 < len(p.rounds) else None
                e = self.place_election(rid, s, flags, cols[rid]["short"])
                rows.append({"rid": rid, "short": cols[rid]["short"], "date": fmt_date(self.dates[rid], loc), "s": s,
                             "how": p.how[rid] if older is not None and older.number != s.number else "",
                             "address": p.addresses.get(rid, ""), "flags": self.flag_view(a, flags, loc),
                             "notes": a.notes.get(s.key, []), "ctrl": ctrl.get(s.key), "ctrl_known": bool(ctrl),
                             "no_ctrl": missing_controllers(ctrl.get(s.key), len(a.round.contestants)),
                             "docs": a.documents.get(s.key, []), "review": a.reviews.get(s.key),
                             "board_docs": self.board_docs_of(rid).get(s.key, []),
                             "n_lists": len(a.round.contestants), "kind": a.round.kind,
                             "top": self.top_three(rid, s.votes) if s.counted else [],
                             "results": self.place_results(rid, s) if s.counted else ([], 0, 0),
                             "e": e, "leader": narrative.short_label(e.leader), "prev_reg": [((self.dates[r] or "")[:4] or cols[r]["short"], p.stations[r].registered)
                                                  for r in p.rounds[i + 1:i + 3] if p.stations[r].registered]})
                story.append(e)
            hints = sorted(codes, key=strength)
            self.write(loc, path + "index.html", "station.html", p=p, s=p.newest, rows=rows, address=p.address,
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
                          self.analyses[rid].documents.get(s.key), self.analyses[rid].reviews.get(s.key),
                          self.board_docs_of(rid).get(s.key)))
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
                                          "observer_reviews.csv", "commission.json")]
                if self.notes_dir:
                    files.append(Path(self.notes_dir) / f"{r}.csv")
            files += [self.archive.dir(rid) / settlements.STORE] + [self.archive.root / f for f in settlements.FIGURE_TABLES]
            files.append(self.archive.root / "geo" / geo.SETTLEMENT_FILE)  # the municipality's map by settlement
            files.append(self.archive.root / maps.COLOURS_FILE)
            links = hashlib.sha256("|".join(self.st_path(rid, s.key) for s in self.analyses[rid].round.stations).encode())
            links.update(repr(sorted(self.city_parts.items())).encode())  # from every election, later ones too
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

    def history_inputs(self, loc: str, code: str) -> str:
        """What a municipality's part across elections is made from: every election it took part in, its rows and
        places there, and the titles of the elections it missed."""
        rids = self.mun_rounds[code]
        newest_first = list(reversed(self.rids))
        places = self.places.in_municipality(code)
        return repr([code, rids, [(rid, self.round_inputs[rid], self.shorts[loc][rid], self.mun_rows[rid][code],
                                   self.mun_votes[rid][code], self.analyses[rid].totals, len(self.flagged[rid]),
                                   self.peers[rid]["mun"]["digest"], self.docs_known[rid],
                                   self.observed[rid][code]) for rid in rids],
                     [(p.id, p.rounds, p.newest.number, p.newest.name, p.former_numbers, self.flagged_in(p))
                      for p in places], [self.shorts[loc][r] for r in newest_first if r not in rids]])

    def history_context(self, loc: str, code: str, rid: str) -> dict:
        """A municipality's other elections, for its page in election `rid`: the strip of its elections (newest
        first, the current one marked) and, on its newest election only, the part across elections: one row per
        election, the narrative, the trends and its polling places (what used to be a page of its own)."""
        rids = self.mun_rounds[code]
        newest_first = list(reversed(self.rids))
        strip = [{"rid": r, "short": self.shorts[loc][r], "date": fmt_date(self.dates[r], loc), "current": r == rid,
                  "href": f"{self.slugs[code]}/" if r == rids[0] else f"r/{r}/m/{code}.html"} for r in rids]
        if rid != rids[0]:
            return {"strip": strip, "history": None}
        rows = [{"rid": r, "short": self.shorts[loc][r], "date": fmt_date(self.dates[r], loc),
                 "m": self.mun_rows[r][code], "top": self.top_three(r, self.mun_votes[r][code])} for r in rids]
        places = []
        mine = self.places.in_municipality(code)
        for p in mine:
            s = p.newest
            places.append({"id": p.id, "path": self.place_path(p), "number": s.number, "name": s.name,
                           "former": p.former_numbers, "n": len(p.rounds), "k": self.flagged_in(p),
                           "last": self.shorts[loc][p.rounds[0]] if p.rounds[0] != rids[0] else "",
                           "order": (p.rounds[0] != rids[0], int(s.number) if s.number.isdigit() else 10 ** 9,
                                     s.number, newest_first.index(p.rounds[0]))})
        places.sort(key=lambda x: x["order"])
        repeat = (sum(1 for x in places if x["k"] >= 1), sum(1 for x in places if x["k"] >= 2))
        network = (sum(1 for p in mine if p.rounds == [rids[0]]),
                   sum(1 for p in mine if rids[0] not in p.stations),
                   sum(1 for p in mine if rids[0] in p.stations and p.former_numbers))
        elections = [self.municipality_election(r, code, self.shorts[loc][r]) for r in rids]
        analysis = narrative.municipality(elections, [self.shorts[loc][r] for r in newest_first if r not in rids],
                                          repeat, network, loc)
        return {"strip": strip, "history": {"rows": rows, "places": places, "analysis": analysis,
                                            "charts": self.trends(rids, elections, "all", loc), "n": len(rids)}}

    def city_link(self, code: str) -> dict | None:
        """The city a municipality is part of, for the line under its title."""
        slug = self.city_of.get(code)
        if not slug:
            return None
        c = self.cities[slug]
        return {"slug": slug, "name": c.name, "n": len(c.codes), "own": c.own == code}

    def city_rows(self, rid: str, city: cities.City) -> list[dict]:
        """The city's municipalities in one election, as municipality rows, the city's own first, then by name."""
        rows = [self.mun_rows[rid][c] for c in city.codes if c in self.mun_rows[rid]]
        return sorted(rows, key=lambda m: city.order(m["code"], m["name"]))

    def city_pages(self, loc: str) -> None:
        """One page per city split into municipalities (g/<slug>.html): its figures added up from its
        municipalities, the result, a map of its municipalities by the leading list, the municipalities (Belgrade's
        in two groups with subtotals), and the same figures at every election. The arithmetic is a municipality's;
        the city is whatever RIK's results put under it."""
        boundaries = None
        for slug, city in sorted(self.cities.items()):
            rids = [r for r in reversed(self.rids) if any(c in self.mun_rows[r] for c in city.codes)]
            if not rids:
                continue
            rid = rids[0]
            inputs = repr([slug, city.codes, [(r, self.round_inputs[r], self.shorts[loc][r],
                                               [self.mun_rows[r].get(c) for c in city.codes],
                                               [self.mun_votes[r].get(c) for c in city.codes], self.analyses[r].totals,
                                               len(self.flagged[r])) for r in rids]])
            self.redirect(loc, f"g/{slug}.html", f"../{slug}/")
            if self.keep(loc, f"{slug}/index.html", self.round_key(rid) + inputs):
                continue
            a = self.analyses[rid]
            sh = self.round_shared(a, loc)
            rows = self.city_rows(rid, city)
            codes = {m["code"] for m in rows}
            sts = [s for s in a.round.stations if s.municipality_code in codes]
            total = cities.add_up(rows, sts)
            votes = [sum(self.mun_votes[rid][m["code"]][i] for m in rows) for i in range(len(a.round.contestants))]
            mres, top, _ = vote_view(a.round.contestants, votes, a.totals, [])
            index = leading(votes)
            # the municipalities on a map, coloured by the list first in each, as the settlements are
            if boundaries is None:
                boundaries = geo.load(self.archive.root / "geo" / "municipalities.json") or {"features": []}
            by_code = {f["properties"].get("code"): f for f in boundaries["features"]}
            feats, results = [], {}
            for m in rows:
                f = by_code.get(m["code"])
                label = cities.short_name(m["name"])
                mv = self.mun_votes[rid][m["code"]]
                lead = leading(mv)
                order = sorted(range(len(mv)), key=lambda k: -mv[k])
                valid = sum(mv) or 1
                results[label] = {"leader": lead, "share": mv[lead] / valid if lead is not None else None,
                                  "second": mv[order[1]] / valid if len(order) > 1 and lead is not None else None}
                if f:
                    feats.append({"type": "Feature", "geometry": f["geometry"],
                                  "properties": {"code": m["code"], "name": label, "census": label}})
            short = sh["short"]
            city_map, map_key = maps.settlement_map(feats, results, sh["ranks"], short, city.name,
                                                    lambda x: fmt_pct(x, loc, 1)) if len(feats) > 1 else ("", [])
            legend = maps.legend(results, sh["ranks"], short) if city_map else []
            groups = []
            for m in rows:
                g = city.group_of(m["code"])
                if not groups or groups[-1]["key"] != g:
                    groups.append({"key": g, "rows": []})
                groups[-1]["rows"].append(m)
            for g in groups:
                g["sum"] = cities.add_up(g["rows"], [s for s in sts if s.municipality_code in {m["code"] for m in g["rows"]}])
                gv = [sum(self.mun_votes[rid][m["code"]][i] for m in g["rows"]) for i in range(len(a.round.contestants))]
                g["top"] = self.top_three(rid, gv)
            leaders = {}
            for m in rows:
                mv = self.mun_votes[rid][m["code"]]
                lead = leading(mv)
                leaders[m["code"]] = (lead, mv[lead] / sum(mv)) if lead is not None and sum(mv) else (None, None)
            history = []
            for r in rids:
                hrows = self.city_rows(r, city)
                hcodes = {m["code"] for m in hrows}
                hv = [sum(self.mun_votes[r][m["code"]][i] for m in hrows)
                      for i in range(len(self.analyses[r].round.contestants))]
                history.append({"rid": r, "short": self.shorts[loc][r], "date": fmt_date(self.dates[r], loc),
                                "m": cities.add_up(hrows, [s for s in self.analyses[r].round.stations
                                                           if s.municipality_code in hcodes]),
                                "top": self.top_three(r, hv), "n": len(hrows)})
            # the map's municipalities are clickable: each one's stations, from this JSON (no server, no third party)
            tt = lambda key, **kw: t(key, loc, **kw)  # noqa: E731
            show = latin if loc == "en" else (lambda x: x)
            root = "../"
            muns = {}
            for m in rows:
                label = cities.short_name(m["name"])
                sts = sorted((s for s in a.round.stations if s.municipality_code == m["code"]),
                             key=lambda s: (int(s.number) if s.number.isdigit() else 0, s.number))
                muns[show(label)] = {"name": show(m["name"]), "href": root + PREFIX[loc] + self.slugs[m["code"]] + "/",
                                     "stations": [[s.number, show(s.name), round(s.turnout, 4) if s.counted and s.turnout is not None else None,
                                                   len(sh["by_station"].get(s.key, [])),
                                                   root + PREFIX[loc] + self.st_path(rid, s.key)] for s in sts]}
            city_data = json.dumps({"muns": muns, "i18n": {"title": tt("city_panel_title", name="{name}", n="{n}"),
                                                            "close": tt("vi_panel_close"), "station": tt("station"),
                                                            "turnout": tt("turnout"), "flags": tt("co_tile_flagged"),
                                                            "page": tt("city_panel_page"), "stationNo": tt("station_no"),
                                                            "more": tt("city_panel_more", n="{n}"), "hint": tt("city_panel_hint")}},
                                   ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
            self.write(loc, f"{slug}/index.html", "city.html", city=city, slug=slug, rows=rows, total=total, mres=mres,
                       city_data=city_data,
                       mtop=top, index=index, groups=groups, leaders=leaders, labels=self.labels[rid],
                       city_map=city_map, map_key=map_key, legend=legend, history=history,
                       country=sh["country"], short_name=cities.short_name, **sh["common"])

    def municipality_pages(self, loc: str) -> None:
        """One page per municipality at m/<code>.html, the address the search and the index open: the coordinator's
        page in its newest election, with its other elections at the end (8 Nov 2026; before that this address held
        a page across elections alone, and the coordinator's page was only under r/<id>/m/)."""
        for code, rids in self.mun_rounds.items():
            rid = rids[0]
            slug = self.slugs[code]
            self.redirect(loc, f"m/{code}.html", f"../{slug}/")
            for other in cities.aliases(slug):
                self.redirect(loc, f"{other}/index.html", f"../{slug}/")
            if self.keep(loc, f"{slug}/index.html", self.round_key(rid) + self.history_inputs(loc, code)):
                continue
            a = self.analyses[rid]
            self.write(loc, f"{slug}/index.html", "municipality.html", canonical=True, city=self.city_link(code),
                       **self.municipality_context(a, loc, self.mun_rows[rid][code], f"{slug}/index.html"),
                       **self.history_context(loc, code, rid))

    def redirect(self, loc: str, page: str, target: str) -> None:
        """A one-line page at an old address that leads to the new one (GitHub Pages has no server redirects)."""
        if not self.keep(loc, page, "redirect|" + target):
            self.write(loc, page, "redirect.html", target=target)

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
        # the Explore page: every polling station of an election, and the municipalities' boundaries for its map
        for rid in self.rids:
            self.put(f"api/r/{rid}/stations.json", dump(self.round_data(rid)))
            self.put(f"api/r/{rid}/commissions.csv", publishing.to_csv(self.publishing_of(rid)[0]))
            self.put(f"api/r/{rid}/settlements.csv", bysettlement.to_csv(self.by_settlement_of(rid),
                                                                      self.analyses[rid].round.contestants))
        boundaries = geo.load(self.archive.root / "geo" / "municipalities.json")
        if boundaries:
            self.put("api/geo/municipalities.json", json.dumps(self.map_of(boundaries), ensure_ascii=False,
                                                               separators=(",", ":")))

    def map_of(self, boundaries: dict) -> dict:
        """The boundaries of the municipalities RIK counts by, joined by code. A city whose city municipalities RIK
        counts one by one (Belgrade, Niš and others) has its own boundary in OpenStreetMap too; RIK never uses its
        code, so it is left out rather than drawn over its parts. Kosovo and Metohija's, in RIK's division, come from
        another dataset, which the map then credits too (kim). Names come from RIK, in the page's language."""
        def props(p: dict) -> dict:
            out = {"code": p["code"]}
            if p.get("source") == "ELWar":
                out["kim"] = 1
            if p.get("none"):  # in Kosovo and Metohija, with no station in any election here: drawn grey, named
                out.update({"none": 1, "name": p.get("name", "")})
            return out
        feats = [{"type": "Feature", "properties": props(f["properties"]), "geometry": f["geometry"]}
                 for f in boundaries.get("features", [])
                 if f["properties"].get("code") in self.mun_rounds or f["properties"].get("none")]
        return {"type": "FeatureCollection", "attribution": boundaries.get("attribution", ""),
                "license": boundaries.get("license", ""), "source": boundaries.get("source", ""), "features": feats}

    def round_data(self, rid: str) -> dict:
        """One election's polling stations for the Explore page, as columns of equal length so the file stays small:
        municipality code, number, name, place across elections, the numbers from the minutes, how many flags and in
        which groups (bits in the order of GROUPS), which lists appointed a member or deputy of the extended
        composition (bit n-1 for ballot number n; null where no decision was read), whether RIK published an
        observers' record, the hours from the polls closing to the upload of the station's first minutes (null
        when none is known), each list's votes, by ballot number, and the station's settlement ("set": its index in
        "settlements", null where it isn't known) with the census's figures for it: [name as the census prints it,
        1 for urban, population in 2011, in 2022, people aged 65 or more], null where the census gives none."""
        a = self.analyses[rid]
        ctrl = self.ctrl_of(rid)
        bit = {g: 1 << i for i, g in enumerate(GROUPS)}
        cols: dict[str, list] = {k: [] for k in ("mc", "no", "name", "place", "reg", "voted", "box", "valid", "invalid",
                                                "flags", "groups", "ctrl", "obs", "min", "set")}
        joined, figures = self.settlements_of(rid), self.figures
        places: dict[tuple[str, str], int] = {}
        for key in sorted({(e["u"], e["s"]) for e in joined.values() if (e["u"], e["s"]) in figures}):
            places[key] = len(places)
        close = publishing.closing(self.dates[rid] or "")
        votes: list[list] = [[] for _ in a.round.contestants]
        for s in a.round.stations:
            p = self.places.of(rid, s.key)
            flags = self.flagged[rid].get(s.key, [])
            hours = publishing.hours_after(publishing.first_minutes(a.documents.get(s.key, [])), close)
            lists = (ctrl.get(s.key) or {}).get("lists")
            mask = None
            if lists is not None:
                mask = 0
                for n, v in lists.items():
                    if n.isdigit() and 0 < int(n) <= 31 and (v.get("member") or v.get("deputy")):
                        mask |= 1 << (int(n) - 1)
            row = {"mc": s.municipality_code, "no": s.number, "name": s.name, "place": p.id if p else "",
                   "reg": s.registered, "voted": s.voted, "box": s.ballots, "valid": s.valid, "invalid": s.invalid,
                   "flags": len(flags), "groups": sum({bit[f.check.group] for f in flags}), "ctrl": mask,
                   "obs": int(any(d.kind == "observers" for d in a.documents.get(s.key, []))),
                   "min": None if hours is None else round(hours, 1)}
            e = joined.get(s.key)
            row["set"] = places.get((e["u"], e["s"])) if e else None
            for k, v in row.items():
                cols[k].append(v)
            for i in range(len(votes)):
                votes[i].append(s.votes[i] if i < len(s.votes) else None)
        return {"id": rid, "kind": a.round.kind, "date": self.dates[rid], "title": a.round.title,
                "contestants": [{"n": c.number, "name": c.name, "short": c.short} for c in a.round.contestants],
                "municipalities": {code: m["name"] for code, m in self.mun_rows[rid].items()},
                "controllers": bool(ctrl), "observers": self.docs_known[rid], "groups": GROUPS, "stations": cols,
                "votes": votes, "settlements": [[place, int(f.urban), f.pop2011, f.pop2022, f.old]
                                                for (unit, place), f in ((k, figures[k]) for k in places)]}

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
        """search.json for the search on the home page, kept small. Municipalities: [name, code, elections, newest
        election]. Polling places: [municipality, number, name, page, elections flagged, elections, former numbers],
        flagged ones first; page is left out ("") when it is the municipality code and number. Both lead to their one
        page (m/<code>.html, s/<place>.html), which opens on the newest election; the page builds the labels and links."""
        conv = (lambda text: text) if loc == "cyr" else latin
        names = {code: self.mun_rows[rids[0]][code]["name"] for code, rids in self.mun_rounds.items()}
        order = sorted(names, key=lambda code: latin(names[code]))
        at = {code: i for i, code in enumerate(order)}
        rows = []
        for p in self.places.places:
            s, k = p.newest, self.flagged_in(p)
            page = "" if p.id == station_path(s.key)[2:-5] else p.id[len(p.code) + 1:]  # the tail of its address
            rows.append((-k, latin(names[p.code]), int(s.number) if s.number.isdigit() else 0, s.number,
                         [at[p.code], s.number, conv(s.name), page, k, len(p.rounds), ", ".join(p.former_numbers)]))
        rows.sort(key=lambda r: r[:4])
        data = {"m": [[conv(names[c]), c, len(self.mun_rounds[c]), self.mun_rounds[c][0], self.slugs[c]] for c in order],
                "g": [[conv(c.name), slug, len(c.codes)] for slug, c in sorted(self.cities.items())],
                "s": [r[4] for r in rows]}
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
        self.put("static/labels.css", cell_labels())
        self.put(".nojekyll", "")
        self.cache: dict = {}
        self.ctrl_cache: dict = {}
        self.board_docs_cache: dict = {}
        self.commission_cache: dict = {}
        self.publishing_cache: dict = {}
        self.city_cache: dict = {}
        self.city_parts: dict = {}
        self.settlement_cache: dict = {}
        self.figures_cache: dict | None = None
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
        self.shorts = {loc: {a.round.id: self.short_title(a.round, loc) for a in oldest_first} for loc in BUILT}
        self.round_inputs = {a.round.id: repr((a.round.kind, self.dates[a.round.id], self.labels[a.round.id],
                                               [(c.number, c.name, c.short) for c in a.round.contestants]))
                             for a in oldest_first}
        self.round_keys: dict[str, str] = {}
        self.shared_cache: dict = {}  # round_shared(), per election and language
        # rounds whose documents are known: RIK's register was read, or the results file lists observers' records
        self.docs_known = {a.round.id: documents.path(self.archive.dir(a.round.id)).exists()
                           or any(d.kind == "observers" for docs in a.documents.values() for d in docs)
                           for a in oldest_first}
        self.observed = {a.round.id: Counter(s.municipality_code for s in a.round.stations
                                             if any(d.kind == "observers" for d in a.documents.get(s.key, [])))
                         for a in oldest_first}  # municipality code → its stations with an observers' record
        self.mun_rows, self.mun_votes = {}, {}
        self.mun_rounds: dict[str, list[str]] = defaultdict(list)  # municipality code → round ids, newest first
        self.list_colours = maps.load_colours(self.archive.root / maps.COLOURS_FILE)
        self.peers: dict[str, dict] = {}  # round id → sorted values to rank stations and municipalities by
        for a in rounds:
            rid = a.round.id
            self.mun_rows[rid] = {m["code"]: m for m in self.municipalities(a)}
            self.mun_votes[rid] = municipality_votes(a.round)
            for code in self.mun_rows[rid]:
                self.mun_rounds[code].append(rid)
            self.peers[rid] = peer_values(a.round, self.mun_rows[rid])
        # which city municipalities belong to a city, from every election's names and districts
        self.city_parts = commission.city_parts(s for a in rounds for s in a.round.stations)
        # the cities split into several municipalities (Belgrade, Niš, …): one page each, and an entry in the search
        self.cities = cities.cities(self.city_parts, [s for a in rounds for s in a.round.stations])
        self.city_of = {code: slug for slug, c in self.cities.items() for code in c.codes}
        # every municipality's address by name (/novi-sad/), the cities' too (/beograd/); the old m/<code>.html and
        # g/<slug>.html stay as one-line pages that lead there
        newest_names = {code: rows[0] for code, rows in ((c, [self.mun_rows[r][c]["name"] for r in rs])
                                                         for c, rs in self.mun_rounds.items())}
        self.slugs = cities.slugs(newest_names, set(self.mun_rows[rids[-1]]) if rids else set(), set(self.cities),
                                  {c.own for c in self.cities.values() if c.own})
        top = max(overall["counts"].values(), default=0) or 1
        appear = [{"code": c.code, "group": c.group, "n": overall["counts"][c.code],
                   "w": 100 * overall["counts"][c.code] / top}
                  for c in sorted(CHECKS, key=lambda c: -overall["counts"].get(c.code, 0)) if overall["counts"].get(c.code)]
        example = rep_rows[0] if rep_rows and rep_rows[0]["k"] >= 2 else None
        share = {a.round.id: len(a.by_station) / a.totals.stations if a.totals.stations else 0.0 for a in rounds}
        share_top = max(share.values(), default=0) or 1
        for rid in rids:  # loaded once here, before the languages are written side by side
            self.ctrl_of(rid)
            self.commission_of(rid)
            self.city_docs_of(rid)
            self.publishing_of(rid)
            self.by_settlement_of(rid)
        home = self.home_data(rounds[0] if rounds else None)
        cards = self.highlights_of(rids[-1]) if rids else {}

        def pages_in(loc: str) -> None:
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
                       checks=CHECKS, groups=GROUPS, home=home, cards=cards)
            self.write(loc, "municipalities.html", "municipalities.html", rows=self.municipality_index(loc),
                       last=self.shorts[loc][rids[-1]] if rids else "", last_rid=rids[-1] if rids else "")
            meta = json.dumps(self.explore_meta(loc), ensure_ascii=False, separators=(",", ":"))
            self.write(loc, "explore.html", "explore.html", meta=Markup(meta.replace("</", "<\\/")))
            self.write(loc, "elections.html", "elections.html", rounds=summaries)
            self.write_search(loc)
            self.city_pages(loc)
            self.write(loc, "guide.html", f"guide.{'en' if loc == 'en' else 'sr'}.html",
                       latest=summaries[0] if summaries else None)
            self.write(loc, "about.html", "about.html", checks=CHECKS, groups=GROUPS)
            groups = [(k, [r for r in rep_rows if r["k"] == k]) for k in sorted({r["k"] for r in rep_rows}, reverse=True)]
            rep_mun_options = sorted({(r["station"].municipality_code, r["station"].municipality) for r in rep_rows},
                                     key=lambda x: collate(latin(x[1]) if loc == "en" else x[1], loc))
            self.write(loc, "repeat.html", "repeat.html", rows=rep_rows, once=rep_once, n2=rep_n2, muns=rep_muns, groups=groups,
                       rounds=columns, same=rep_same, checks=CHECKS, group_of=group_of, example=example,
                       st_path=self.st_path, mun_options=rep_mun_options, slugs=self.slugs)
            cols = {c["id"]: c for c in columns}
            self.place_pages(loc, cols)
            self.municipality_pages(loc)
            for a in rounds:
                self.round_pages(a, loc)

        self.side_by_side([lambda loc=loc: pages_in(loc) for loc in BUILT])
        self.write_api()
        # GitHub Pages serves this file for a missing page at any depth, so its links are absolute.
        self.write("lat", "404.html", "404.html", root=self.site_url,
                   link=lambda target: self.site_url + target)
        self.put("feed.sr.xml", feed.build(self.archive.root, self.archive, "lat", self.site_url))
        entries = feed.load_entries(self.archive.root)
        for code, rids in self.mun_rounds.items():  # one feed per municipality, for observers who follow one place
            name = self.mun_rows[rids[0]][code]["name"]
            self.put(f"feed/{code}.sr.xml", feed.build(self.archive.root, self.archive, "lat", self.site_url,
                                                       municipality=(code, name), entries=entries))
        self.finish()
        return self.out

    def side_by_side(self, jobs: list) -> None:
        """Run jobs that write pages (one per language) each in a process of its own, at the same time, and keep
        what they wrote and recorded as if they had run here one after another. Where processes can't be forked
        (Windows), or IZBORI_SERIAL is set, they run here in turn."""
        import multiprocessing
        import os
        if len(jobs) < 2 or os.environ.get("IZBORI_SERIAL") or "fork" not in multiprocessing.get_all_start_methods():
            for job in jobs:
                job()
            return
        ctx = multiprocessing.get_context("fork")
        running = []
        for job in jobs:
            receive, send = ctx.Pipe(duplex=False)
            proc = ctx.Process(target=_write_pages, args=(self, job, send))
            proc.start()
            send.close()
            running.append((proc, receive))
        errors = []
        for proc, receive in running:
            try:
                produced, state, kept, rendered, error = receive.recv()
            except EOFError:
                produced, state, kept, rendered, error = set(), {}, 0, 0, "a process writing pages died"
            proc.join()
            if error:
                errors.append(error)
            self.produced |= produced
            self.state.update(state)
            self.kept += kept
            self.rendered += rendered
        if errors:
            raise RuntimeError("\n".join(errors))

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

    def round_shared(self, a: Analysis, loc: str) -> dict:
        """What every municipality page of one election shares: the stations by municipality, the controllers, the
        settlements, the lists' colour slots and short labels, the country's figures, the previous election's rows.
        Computed once per election and language."""
        rid = a.round.id
        if (rid, loc) in self.shared_cache:
            return self.shared_cache[(rid, loc)]
        municipalities = list(self.mun_rows[rid].values())
        by_station = self.flagged[rid]
        ctrl = self.ctrl_of(rid)
        ctrl_table, ctrl_readable = ctrl_rows(a.round.contestants, ctrl.values())
        label = self.contestant_label(a, loc)
        base = f"r/{rid}/"
        common = {"rebuilt": self.archive.meta(rid).get("source") == "results_app",
                  "ctrl_readable": ctrl_readable, "a": a, "rnd": a.round, "totals": a.totals, "base": base,
                  "view": self.round_view(a), "snapshots": a.snapshots, "label": label,
                  "rtitle": self.round_title(a.round, loc), "rshort": self.short_title(a.round, loc),
                  "st_path": self.st_path, "ctrl": ctrl, "ctrl_known": bool(ctrl), "ctrl_table": ctrl_table}
        by_code: dict[str, list] = defaultdict(list)
        for s in a.round.stations:
            by_code[s.municipality_code].append(s)
        settl = self.settlements_of(rid)
        profiles = coordinator.profiles(self.mun_rows[rid], by_code, settl, self.figures)
        shapes = geo.settlements_by_municipality(self.archive.root / "geo" / geo.SETTLEMENT_FILE)
        ranks = {i: k + 1 for k, i in enumerate(sorted(range(len(a.round.contestants)), key=lambda i: -a.totals.votes[i]))}
        manual = {i: self.list_colours[(rid, c.number)] for i, c in enumerate(a.round.contestants)
                  if (rid, c.number) in self.list_colours}
        ranks = maps.slots(ranks, manual)  # from here on: each list's colour slot, the maintainer's where set
        short = {i: narrative.short_label(self.labels[rid][i]) for i in range(len(a.round.contestants))}
        if loc == "en":
            short = {i: latin(v) for i, v in short.items()}
        domestic = [m for m in municipalities if m["kind"] == "domestic"]
        country = {"turnout": a.totals.turnout, "invalid": a.totals.invalid_share,
                   "flagged_share": (sum(m["flagged"] for m in domestic) / sum(m["stations"] for m in domestic))
                   if domestic else None}
        prev = a.previous[0] if a.previous else None
        prev_rows = self.mun_rows.get(prev, {}) if prev else {}
        both = [c for c in prev_rows if c in self.mun_rows[rid] and self.mun_rows[rid][c]["kind"] == "domestic"]
        country["registered_change"] = (sum(self.mun_rows[rid][c]["registered"] for c in both)
                                        / sum(prev_rows[c]["registered"] for c in both) - 1) if both and sum(
            prev_rows[c]["registered"] for c in both) else None
        country["prev_year"] = (self.dates.get(prev) or "")[:4] if prev else ""
        settlement_of = lambda s: (settl.get(s.key) or {}).get("s", "")  # noqa: E731
        sh = dict(rid=rid, base=base, municipalities=municipalities, by_station=by_station, ctrl=ctrl, common=common,
                  by_code=by_code, settl=settl, profiles=profiles, shapes=shapes, ranks=ranks, short=short,
                  country=country, prev_rows=prev_rows, settlement_of=settlement_of)
        self.shared_cache[(rid, loc)] = sh
        return sh

    def municipality_context(self, a: Analysis, loc: str, m: dict, page: str) -> dict:
        """Everything municipality.html needs for one municipality in one election (the coordinator's page), written
        at `page` (the stations' links in the page's JSON are relative to it)."""
        sh = self.round_shared(a, loc)
        rid, base, by_code, settl, ctrl, by_station = sh["rid"], sh["base"], sh["by_code"], sh["settl"], sh["ctrl"], sh["by_station"]
        profiles, shapes, ranks, short, country, prev_rows = (sh["profiles"], sh["shapes"], sh["ranks"], sh["short"],
                                                              sh["country"], sh["prev_rows"])
        settlement_of, common = sh["settlement_of"], sh["common"]
        sts = sorted(by_code[m["code"]], key=lambda s: (int(s.number) if s.number.isdigit() else 0, s.number))
        rows = [{"s": s, "flags": self.flag_view(a, by_station.get(s.key, []), loc),
                 "notes": a.notes.get(s.key, []), "docs": a.documents.get(s.key, []),
                 "settlement": settlement_of(s)} for s in sts]
        votes = self.mun_votes[rid][m["code"]]
        mctrl, mreadable = ctrl_rows(a.round.contestants, [ctrl[s.key] for s in sts if s.key in ctrl])
        mres, top, by_st = vote_view(a.round.contestants, votes, a.totals, [s for s in sts if s.counted])
        index = leading(votes)
        number = a.round.contestants[index].number if index is not None else None
        flags_of = {s.key: by_station.get(s.key, []) for s in sts}
        root = "../" * (PREFIX[loc] + page).count("/")
        hrefs = {s.key: root + PREFIX[loc] + self.st_path(rid, s.key) for s in sts}
        weak = coordinator.weak_spots(sts, flags_of, self.places.in_municipality(m["code"]), self.flagged,
                                      ctrl, number, settlement_of, a.reviews) if number is not None else None
        devs = coordinator.deviations(sts, votes, index) if index is not None else []
        prev_m = prev_rows.get(m["code"])
        compare = {"similar": coordinator.similar(m["code"], profiles, self.mun_rows[rid]), "country": country,
                   "rank_turnout": rank_of(m["turnout"], self.peers[rid]["mun"]["turnout"]),
                   "rank_invalid": rank_of(m["invalid"], self.peers[rid]["mun"]["invalid"]),
                   "prev_registered": prev_m["registered"] if prev_m and prev_m["registered"] else None}
        tt = lambda key, **kw: t(key, loc, **kw)  # noqa: E731
        show = latin if loc == "en" else (lambda x: x)
        data = json.dumps({"rid": rid, "default": index, "name": show(m["name"]),
                           "lists": [{"n": c.number, "label": show(narrative.short_label(self.labels[rid][i])),
                                      "slot": ranks.get(i, 9), "country": a.totals.share_of_valid(i)}
                                     for i, c in enumerate(a.round.contestants)],
                           "turnout": {"mun": m["turnout"], "country": country["turnout"]},
                           "i18n": {"rule3": tt("co_w3_rule", number="{number}"), "ofRead": tt("co_w3_of", n="{n}"),
                                    "chartResult": tt("vi_chart_result"), "chartPlaces": tt("vi_chart_places"), "chartPlacesNote": tt("vi_chart_places_note"),
                                    "country": tt("vi_chart_country"), "countryShort": tt("vi_chart_country_short"), "keyLabel": tt("vi_key_label"),
                                    "stations": tt("co_stations_word"), "stationNo": tt("station_no"),
                                    "panelTitle": tt("vi_panel_title", name="{name}", n="{n}"),
                                    "panelClose": tt("vi_panel_close"), "turnout": tt("turnout"), "station": tt("station"),
                                    "myList": tt("co_col_mine"), "controller": tt("co_col_ctrl"),
                                    "panelHint": tt("vi_panel_hint"), "modeLabel": tt("vi_mode_label"), "modeLead": tt("vi_mode_lead"), "modeMine": tt("vi_mode_mine"), "rampLead": tt("vi_ramp_lead"), "rampMine": tt("vi_ramp_mine", list="{list}"),
                                    "legendNc": tt("co_legend_nc"), "rest": tt("co_dev_rest", n="{n}"),
                                    "devNote": tt("co_dev_note", avg="{avg}"), "member": tt("co_ctrl_member"),
                                    "deputy": tt("co_ctrl_deputy"), "none": tt("co_ctrl_none"),
                                    "notRead": tt("co_not_read")},
                           "stations": coordinator.station_json(sts, ctrl, flags_of, settlement_of,
                                                                len(a.round.contestants), hrefs, show)},
                          ensure_ascii=False, separators=(",", ":"))
        flag_text = {s.key: {f["code"]: f["text"] for f in r["flags"]} for s, r in zip(sts, rows)}
        villages = coordinator.by_settlement(sts, settl, self.figures, index)
        village_leaders = coordinator.leaders(villages)
        results = {v["name"]: v for v in villages if v["name"]}
        feats = shapes.get(m["code"], [])
        village_map, village_key = maps.settlement_map(feats, results, ranks, short, m["name"], lambda x: fmt_pct(x, loc, 1)) \
            if feats and len(results) > 1 else ("", [])
        village_legend = maps.legend(results, ranks, short) if village_map else []
        top2 = sorted(range(len(votes)), key=lambda k: -votes[k])[:2] if any(votes) else []
        village_facts = [tt("vi_fact_turnout", hi=f["hi"], hv=fmt_pct(f["hv"], loc, 1), lo=f["lo"], lv=fmt_pct(f["lv"], loc, 1))
                         if f["kind"] == "turnout" else
                         tt("vi_fact_list", list=short[f["index"]], hi=f["hi"], hv=fmt_pct(f["hv"], loc, 1), lo=f["lo"],
                            lv=fmt_pct(f["lv"], loc, 1))
                         for f in coordinator.facts(villages, top2)] if village_map else []
        if village_map and m["turnout"] is not None and country["turnout"] is not None:
            village_facts.append(tt("vi_fact_mun", t=fmt_pct(m["turnout"], loc, 1), c=fmt_pct(country["turnout"], loc, 1)))
        return dict(m=m, rows=rows, mvotes=votes,
                   mctrl=mctrl, mreadable=mreadable, mres=mres, mtop=top, mby=by_st, weak=weak, devs=devs,
                   index=index, number=number, compare=compare, mun_data=data.replace("<", "\\u003c"),
                   ctrl_of=coordinator.controller_of, rules=RULES, flag_text=flag_text, labels=self.labels[rid],
                   settlement_by_key={s.key: settlement_of(s) for s in sts}, villages=villages,
                   village_leaders=village_leaders, village_map=village_map, village_legend=village_legend,
                   village_facts=village_facts, village_key=village_key,
                   mapped=sum(1 for f in feats if f["properties"].get("census") in results),
                   cdocs=self.commission_of(rid).get(m["code"], []),
                   citydocs=self.city_docs_of(rid)[0].get(m["code"]), **common)

    def round_pages(self, a: Analysis, loc: str) -> None:
        rid = a.round.id
        base = f"r/{rid}/"
        pages = {page: self.round_key(rid) for page in (base + "index.html", base + "check.html", base + "changes.html",
                                                        base + "commissions.html", base + "settlements.html")}
        # a municipality's page also carries its other elections (the strip, and the history on its newest)
        pages.update({base + f"m/{code}.html": self.round_key(rid) + self.history_inputs(loc, code)
                      for code in self.mun_rows[rid]})
        if all([self.keep(loc, page, key) for page, key in pages.items()]):  # a list: every page is recorded
            return
        stations = {s.key: s for s in a.round.stations}
        by_station = self.flagged[rid]
        municipalities = list(self.mun_rows[rid].values())
        totals = a.totals
        top2 = stats.top_two(totals.votes) if totals.votes else []
        label = self.contestant_label(a, loc)
        context_stats = {
            "hist": svg.histogram(stats.turnout_histogram(a.round), loc),
            "digits": [(label(i + 1), d, svg.digits(d, loc)) for i in top2
                       if (d := stats.last_digits(a.round, i)) is not None],
            "round": stats.round_percentages(a.round, top2),
            "local_round": stats.round_percentages_by_municipality(a.round, top2),
            "local_digits": stats.last_digits_by_municipality(a.round),
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
        common = self.round_shared(a, loc)["common"]
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
                   groups=GROUPS, counts=counts, group_counts=group_counts, **common)

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
        prow, ptotal = self.publishing_of(rid)
        self.write(loc, base + "commissions.html", "commissions.html", rows=prow, total=ptotal,
                   slow_hours=publishing.SLOW_HOURS, late_hours=publishing.LATE_HOURS, **common)
        self.write(loc, base + "settlements.html", "settlements.html", sx=self.by_settlement_of(rid),
                   dims=bysettlement.DIMENSIONS, **common)

        for m in self.round_shared(a, loc)["municipalities"]:
            code = m["code"]
            self.write(loc, base + f"m/{code}.html", "municipality.html", canonical=False, city=self.city_link(code),
                       **self.municipality_context(a, loc, m, base + f"m/{code}.html"),
                       **self.history_context(loc, code, rid))


def _write_pages(site: Site, job, send) -> None:
    """In a forked process: run the job and send back what it wrote and recorded."""
    import traceback
    site.produced, site.state, site.kept, site.rendered = set(), {}, 0, 0
    error = ""
    try:
        job()
    except Exception:  # noqa: BLE001 - reported to the parent, which fails the build
        error = traceback.format_exc()
    send.send((site.produced, site.state, site.kept, site.rendered, error))
    send.close()


LABELLED = ("station", "stations", "registered", "voted", "turnout", "invalid", "top_three", "flags", "flagged")


def cell_labels() -> str:
    """The labels a table across elections shows inside each cell on a phone, for every language: once here
    rather than on every cell of every page (cells carry the class l-<key>)."""
    def quote(text: str) -> str:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    rules = []
    for loc in BUILT:
        for key in LABELLED:
            text = t(key, loc)
            text = latin(text) if loc == "lat" else text
            rules.append(f"  :lang({LANG_ATTR[loc]}) table.history td.l-{key}::before {{ content: {quote(text)}; }}")
    return "@media (max-width: 600px) {\n" + "\n".join(rules) + "\n}\n"


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


INDENT = re.compile(r"\n[ \t]+")
BLANK = re.compile(r"\n{2,}")


def compact(html: str) -> str:
    """The page without the templates' indentation: a line break between tags renders the same as a line break
    and eight spaces, and the indentation was 5–6% of the site (Nov 2026). Text keeps its single spaces; nothing
    between tags on one line is touched, so inline elements stay apart. No page has a <pre>."""
    return BLANK.sub("\n", INDENT.sub("\n", html))


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


def missing_controllers(c: dict | None, n_lists: int) -> list[int] | None:
    """Ballot numbers with neither a member nor a deputy on the board; None when no decision was read."""
    if not c or c.get("lists") is None:
        return None
    have = {int(k) for k, v in c["lists"].items() if v.get("member") or v.get("deputy")}
    return [n for n in range(1, n_lists + 1) if n not in have]


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
