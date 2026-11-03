"""The same polling place followed through every archived election.

RIK numbers polling stations per municipality, and the numbers, names and areas change between elections. Going
from the newest election back, each station is joined to the place it continues within its municipality:

1. by address, where the decisions on polling boards gave one;
2. then by name;
3. then by number. A number alone never joins two stations whose addresses or names clearly differ: those are two
   places.

Stations that share an address or a name (one school, several stations) are paired by equal number first, then in
number order. Names and addresses are compared by their telling words, so "ОШ Вељко Петровић" and "Основна школа
Вељко Петровић" are one name, and a name made only of words like "school" tells nothing.

The site's search and its pages across elections show places. The station checks and the table of stations flagged
again and again still recognise a station by municipality and number."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from izbori.boards import tokens
from izbori.checks import GENERIC
from izbori.model import Station

HOW = ("address", "name", "number")


def words(text: str) -> frozenset[str]:
    """The words that tell one place from another; empty when there are none."""
    return frozenset(tokens(text) - GENERIC) if text else frozenset()


def _order(number: str) -> tuple[int, str]:
    return (int(number), "") if number.isdigit() else (10 ** 9, number)


@dataclass
class Place:
    code: str  # municipality code
    rounds: list[str] = field(default_factory=list)  # round ids, newest election first
    stations: dict[str, Station] = field(default_factory=dict)  # round id → that election's station
    how: dict[str, str] = field(default_factory=dict)  # round id → how it was joined to the newer election
    addresses: dict[str, str] = field(default_factory=dict)  # round id → address, where one was read
    id: str = ""  # page name: municipality code and newest number, plus the round when another place has those
    # what the next older election is compared with: the nearest station's number, the nearest known name and address
    number: str = ""
    name: frozenset = frozenset()
    addr: frozenset = frozenset()
    nearest: int = -1  # position, in processing order, of the election the place was last seen in

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
        self.rounds.append(rid)
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


def _pair(places: list[Place], stations: list[Station]) -> list[tuple[Place, Station]]:
    """Places and stations that share an address or a name: equal numbers first, then the rest in number order."""
    out, rest_p, rest_s = [], sorted(places, key=lambda p: (_order(p.number), -p.nearest)), []
    for s in sorted(stations, key=lambda s: _order(s.number)):
        p = next((p for p in rest_p if p.number == s.number), None)
        if p is None:
            rest_s.append(s)
        else:
            rest_p.remove(p)
            out.append((p, s))
    out.extend(zip(rest_p, rest_s))
    return out


def _differ(a: frozenset, b: frozenset) -> bool:
    return bool(a and b and not a & b)


def match(places: list[Place], stations: list[Station], addresses: dict[str, str]) -> list[tuple[Place, Station, str]]:
    """Join one election's stations in a municipality to the places from newer elections."""
    out: list[tuple[Place, Station, str]] = []
    free_p, free_s = list(places), list(stations)
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
            for p, s in _pair(by_p[key], by_s[key]):
                out.append((p, s, how))
                done_p.add(id(p))
                done_s.add(id(s))
        free_p = [p for p in free_p if id(p) not in done_p]
        free_s = [s for s in free_s if id(s) not in done_s]
    for s in sorted(free_s, key=lambda s: _order(s.number)):
        candidates = [p for p in free_p if p.number == s.number
                      and not _differ(p.addr, s_addr[id(s)]) and not _differ(p.name, s_name[id(s)])]
        if candidates:
            p = max(candidates, key=lambda p: p.nearest)  # the one seen in the nearest election
            free_p.remove(p)
            out.append((p, s, "number"))
    return out


def follow(rounds: list[tuple[str, list[Station], dict[str, str]]]) -> Places:
    """rounds: (round id, stations, station key → address), oldest election first."""
    places: list[Place] = []
    open_by_mun: dict[str, list[Place]] = defaultdict(list)
    at: dict[tuple[str, str], Place] = {}
    for position, (rid, stations, addresses) in enumerate(reversed(rounds)):
        by_mun: dict[str, list[Station]] = defaultdict(list)
        for s in stations:
            by_mun[s.municipality_code].append(s)
        for code, sts in by_mun.items():
            joined = match(open_by_mun[code], sts, addresses)
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
    taken_ids: set[str] = set()
    for p in places:  # newest election's places first, so they keep the plain name
        base = f"{p.code}-{re.sub(r'[^0-9A-Za-z_-]', '_', p.newest.number)}"
        p.id = base if base not in taken_ids else f"{base}-{p.rounds[0]}"
        taken_ids.add(p.id)
    return Places(places, at)
