"""The same polling place followed through every archived election.

RIK numbers polling stations per municipality, and the numbers, names and areas change between elections. Going
forward in time, each station is joined to the place it continues within its municipality:

1. by a manual correction in data/places.csv, where a maintainer recorded one;
2. by address, where the decisions on polling boards gave one;
3. then by name;
4. then by number. A number alone never joins two stations whose addresses or names clearly differ: those are two
   places.

Stations that share an address or a name (one school, several stations) are paired by equal number first, then in
number order when as many are left on each side. Names and addresses are compared by their telling words, so "ОШ Вељко Петровић" and "Основна школа
Вељко Петровић" are one name, and a name made only of words like "school" tells nothing.

Because matching runs forward, a new election never changes how the earlier ones were joined. A place's page is
named after its newest station, so names can change; links between elections cannot.

Everything that follows a station across elections uses places: the search and the pages across elections, the
turnout checks against an earlier election, the table of stations flagged again and again, and the target list.

data/places.csv has the columns action, municipality_code, round, number, other_round, other_number, note.
action is "join" (the two stations are one place) or "split" (they never are); the note says why."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from izbori.boards import tokens
from izbori.checks import GENERIC
from izbori.model import Station

HOW = ("manual", "address", "name", "number")
RULES_FILE = "places.csv"


def words(text: str) -> frozenset[str]:
    """The words that tell one place from another; empty when there are none."""
    return frozenset(tokens(text) - GENERIC) if text else frozenset()


def _order(number: str) -> tuple[int, str]:
    return (int(number), "") if number.isdigit() else (10 ** 9, number)


@dataclass
class Rules:
    """Manual corrections: stations that are one place, and stations that never are. Keys are (round, station key)."""
    join: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    split: dict[tuple[str, str], set[tuple[str, str]]] = field(default_factory=lambda: defaultdict(set))


def load_rules(path: Path | None, log=None) -> Rules:
    rules = Rules()
    if path is None or not Path(path).exists():
        return rules
    with open(path, encoding="utf-8", newline="") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            row = {k: (v or "").strip() for k, v in row.items() if k}
            code, action = row.get("municipality_code", ""), row.get("action", "").lower()
            a = (row.get("round", ""), f"{code}/{row.get('number', '')}")
            b = (row.get("other_round", ""), f"{code}/{row.get('other_number', '')}")
            filled = all(row.get(k) for k in ("round", "number", "other_round", "other_number"))
            if not (code and filled and a[0] != b[0] and action in ("join", "split")):
                if log:
                    log(f"{path}:{n}: needs action join or split, a municipality, and two stations in two rounds")
                continue
            if action == "join":
                rules.join[a], rules.join[b] = b, a
            else:
                rules.split[a].add(b)
                rules.split[b].add(a)
    return rules


@dataclass
class Place:
    code: str  # municipality code
    rounds: list[str] = field(default_factory=list)  # round ids, newest election first
    stations: dict[str, Station] = field(default_factory=dict)  # round id → that election's station
    how: dict[str, str] = field(default_factory=dict)  # round id → how it was joined to the earlier elections
    addresses: dict[str, str] = field(default_factory=dict)  # round id → address, where one was read
    id: str = ""  # page name: municipality code and newest number, plus the round when another place has those
    # what the next election is compared with: the latest station's number, the latest known name and address
    number: str = ""
    name: frozenset = frozenset()
    addr: frozenset = frozenset()
    nearest: int = -1  # position, in time, of the election the place was last seen in

    @property
    def newest(self) -> Station:
        return self.stations[self.rounds[0]]

    @property
    def address(self) -> str:
        return next((self.addresses[r] for r in self.rounds if self.addresses.get(r)), "")

    @property
    def former_numbers(self) -> list[str]:
        now = self.newest.number
        return list(dict.fromkeys(self.stations[r].number for r in self.rounds[1:]
                                  if self.stations[r].number != now))

    def add(self, rid: str, s: Station, address: str, how: str, position: int) -> None:
        self.rounds.insert(0, rid)
        self.stations[rid] = s
        self.how[rid] = how
        if address:
            self.addresses[rid] = address
        self.number = s.number
        self.name = words(s.name) or self.name
        self.addr = words(address) or self.addr
        self.nearest = position


@dataclass
class Places:
    places: list[Place]
    at: dict[tuple[str, str], Place]  # (round id, station key) → place

    def of(self, rid: str, key: str) -> Place | None:
        return self.at.get((rid, key))

    def in_municipality(self, code: str) -> list[Place]:
        return [p for p in self.places if p.code == code]


def _pair(places: list[Place], stations: list[Station], apart) -> list[tuple[Place, Station]]:
    """Places and stations that share an address or a name: equal numbers first, then the rest in number order,
    but only when as many are left on each side. That is a renumbered building (stations 10 and 11 became 14 and
    15); with uneven leftovers the name is likely shared by different places (a co-op hall in several villages), so
    those are left to the number."""
    out, rest_p, rest_s = [], sorted(places, key=lambda p: (_order(p.number), -p.nearest)), []
    for s in sorted(stations, key=lambda s: _order(s.number)):
        p = next((p for p in rest_p if p.number == s.number and not apart(p, s)), None)
        if p is None:
            rest_s.append(s)
        else:
            rest_p.remove(p)
            out.append((p, s))
    if len(rest_p) == len(rest_s):
        out.extend((p, s) for p, s in zip(rest_p, rest_s) if not apart(p, s))
    return out


def _differ(a: frozenset, b: frozenset) -> bool:
    return bool(a and b and not a & b)


def contradicts(name: str, address: str) -> bool:
    """Whether an address read from a decision names another building than the station's name in the results (a
    decision filed under the wrong station, or a line that is only the town): such an address isn't used."""
    return _differ(words(name), words(address))


def match(places: list[Place], stations: list[Station], addresses: dict[str, str], rid: str = "",
          rules: Rules | None = None, at: dict | None = None) -> list[tuple[Place, Station, str]]:
    """Join one election's stations in a municipality to the places from earlier elections."""
    out: list[tuple[Place, Station, str]] = []
    free_p, free_s = list(places), list(stations)
    rules = rules or Rules()
    at = at or {}

    def apart(p: Place, s: Station) -> bool:
        banned = rules.split.get((rid, s.key))
        return bool(banned) and any((r, p.stations[r].key) in banned for r in p.rounds)

    for s in list(free_s):
        other = rules.join.get((rid, s.key))
        p = at.get(other) if other else None
        if p is not None and any(p is q for q in free_p):
            free_p = [q for q in free_p if q is not p]
            free_s.remove(s)
            out.append((p, s, "manual"))
    s_name = {id(s): words(s.name) for s in stations}
    s_addr = {id(s): words(addresses.get(s.key, "")) for s in stations}
    for how, of_p, of_s in (("address", lambda p: p.addr, lambda s: s_addr[id(s)]),
                            ("name", lambda p: p.name, lambda s: s_name[id(s)])):
        by_p: dict[frozenset, list[Place]] = defaultdict(list)
        by_s: dict[frozenset, list[Station]] = defaultdict(list)
        for p in free_p:
            if of_p(p):
                by_p[of_p(p)].append(p)
        for s in free_s:
            if of_s(s):
                by_s[of_s(s)].append(s)
        done_p, done_s = set(), set()
        for key in by_p.keys() & by_s.keys():
            for p, s in _pair(by_p[key], by_s[key], apart):
                out.append((p, s, how))
                done_p.add(id(p))
                done_s.add(id(s))
        free_p = [p for p in free_p if id(p) not in done_p]
        free_s = [s for s in free_s if id(s) not in done_s]
    for s in sorted(free_s, key=lambda s: _order(s.number)):
        candidates = [p for p in free_p if p.number == s.number and not apart(p, s)
                      and not _differ(p.addr, s_addr[id(s)]) and not _differ(p.name, s_name[id(s)])]
        if candidates:
            p = max(candidates, key=lambda p: p.nearest)  # the one seen in the nearest election
            free_p.remove(p)
            out.append((p, s, "number"))
    return out


def follow(rounds: list[tuple[str, list[Station], dict[str, str]]], rules: Rules | None = None) -> Places:
    """rounds: (round id, stations, station key → address), oldest election first."""
    places: list[Place] = []
    open_by_mun: dict[str, list[Place]] = defaultdict(list)
    at: dict[tuple[str, str], Place] = {}
    for position, (rid, stations, addresses) in enumerate(rounds):
        by_mun: dict[str, list[Station]] = defaultdict(list)
        for s in stations:
            by_mun[s.municipality_code].append(s)
        for code, sts in by_mun.items():
            joined = match(open_by_mun[code], sts, addresses, rid, rules, at)
            taken = set()
            for p, s, how in joined:
                p.add(rid, s, addresses.get(s.key, ""), how, position)
                at[(rid, s.key)] = p
                taken.add(id(s))
            for s in sts:
                if id(s) not in taken:
                    p = Place(code)
                    p.add(rid, s, addresses.get(s.key, ""), "", position)
                    places.append(p)
                    open_by_mun[code].append(p)
                    at[(rid, s.key)] = p
    # page names: the newest election's places first, in its file's order, so they keep the plain name
    ordered, seen, taken_ids = [], set(), set()
    for rid, stations, _ in reversed(rounds):
        for s in stations:
            p = at[(rid, s.key)]
            if p.rounds[0] == rid and id(p) not in seen:
                seen.add(id(p))
                ordered.append(p)
                base = f"{p.code}-{re.sub(r'[^0-9A-Za-z_-]', '_', p.newest.number)}"
                p.id = base if base not in taken_ids else f"{base}-{rid}"
                taken_ids.add(p.id)
    return Places(ordered, at)
