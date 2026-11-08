"""The municipality's page for a coordinator: what the page needs beyond the round's analysis, as plain data.

A coordinator works one municipality with a few dozen controllers and wants, in this order: the places that keep
coming up, near-unanimity with high turnout, the stations where their own list has nobody on the board, sudden
rises in the register, turnout far from the surroundings, and the places where nobody filed a remark although the
numbers stand out. Every rule here is one sentence on the page and the same for every list and municipality.

The list the coordinator cares about is theirs to pick in the browser; the page is rendered for the municipality's
leading list and `mun.js` redoes the list-dependent parts from the JSON this module also produces.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

SIZE = (5000, 15000, 40000, 100000)  # registered voters: the five size classes municipalities are compared within
URBAN_SHARE = 0.5  # this share of stations in RZS urban settlements or more, and the municipality counts as a town
SIMILAR_MIN = 5  # fewer similar municipalities than this, and the comparison is left out
CARD_ITEMS = 5  # places named on a weak-spot card; the rest are a count and a link
CHART_ROWS = 12  # stations drawn on the deviation chart before "the rest"
STANDS_OUT = {"paper", "unusual"}  # the flag groups that mean the numbers themselves stand out


def size_class(registered: int) -> int:
    return sum(1 for bound in SIZE if registered >= bound)


def urban_share(stations: list, settlements: dict, figures: dict) -> float | None:
    """Share of the municipality's stations placed in an urban settlement; None when fewer than half are placed."""
    known = urban = 0
    for s in stations:
        e = settlements.get(s.key)
        f = figures.get((e["u"], e["s"])) if e and e.get("s") else None
        if f is not None:
            known += 1
            urban += f.urban
    return urban / known if stations and known >= len(stations) / 2 else None


def profiles(mun_rows: dict[str, dict], by_code: dict[str, list], settlements: dict, figures: dict) -> dict[str, dict]:
    """Each domestic municipality's size class and whether it counts as a town."""
    out = {}
    for code, m in mun_rows.items():
        if m["kind"] != "domestic":
            continue
        share = urban_share(by_code.get(code, []), settlements, figures)
        out[code] = {"size": size_class(m["registered"]), "urban": None if share is None else share >= URBAN_SHARE}
    return out


def similar(code: str, profiles_: dict[str, dict], mun_rows: dict[str, dict]) -> dict | None:
    """Mean turnout, invalid share and flagged share of the other municipalities of the same size class and kind
    (town or not); by size alone when the kind is unknown. None with too few of them."""
    me = profiles_.get(code)
    if not me:
        return None
    peers = [c for c, p in profiles_.items() if c != code and p["size"] == me["size"]
             and (me["urban"] is None or p["urban"] is None or p["urban"] == me["urban"])]
    rows = [mun_rows[c] for c in peers if mun_rows[c]["counted"]]
    if len(rows) < SIMILAR_MIN:
        return None

    def avg(key):
        values = [r[key] for r in rows if r.get(key) is not None]
        return mean(values) if values else None
    return {"n": len(rows), "size": me["size"], "urban": me["urban"], "turnout": avg("turnout"),
            "invalid": avg("invalid"), "flagged_share": avg("flagged_share")}


def controller_of(c: dict | None, number: int) -> str | None:
    """'member', 'deputy', 'none', or None when no decision was read for the station."""
    if not c or c.get("lists") is None:
        return None
    entry = c["lists"].get(str(number)) or {}
    if entry.get("member"):
        return "member"
    if entry.get("deputy"):
        return "deputy"
    return "none"


def deviations(stations: list, votes: list[int], index: int) -> list[dict]:
    """Each counted station's share of list `index` against the rest of the municipality (the municipality's
    share without that station), largest difference first."""
    total_votes, total_valid = votes[index], sum(s.valid or 0 for s in stations if s.counted)
    rows = []
    for s in stations:
        if not s.counted or not s.valid:
            continue
        v = s.votes[index] or 0
        rest_valid = total_valid - s.valid
        rest = (total_votes - v) / rest_valid if rest_valid else None
        here = v / s.valid
        rows.append({"s": s, "share": here, "rest": rest, "dev": here - rest if rest is not None else 0.0})
    rows.sort(key=lambda r: -abs(r["dev"]))
    return rows


def weak_spots(stations: list, flags_of: dict[str, list], places: list, flagged_by_round: dict[str, dict],
               ctrl: dict, index: int, settlement_of, reviews: dict) -> dict:
    """The six cards. flags_of: station key → its flags this election; places: the municipality's places across
    elections; flagged_by_round: round id → {station key: flags}; settlement_of(station) → settlement name or ''."""
    codes = {k: {f.code for f in fl} for k, fl in flags_of.items()}
    groups = {k: {f.check.group for f in fl} for k, fl in flags_of.items()}

    repeated = []
    for p in places:
        hits = [r for r in p.rounds if p.stations[r].key in flagged_by_round.get(r, {})]
        if len(hits) >= 2:
            repeated.append({"place": p, "n": len(hits), "of": len(p.rounds), "s": p.newest})
    repeated.sort(key=lambda x: (-x["n"], -x["of"], _num(x["s"].number)))

    # the near-unanimity rule already asks for high turnout (checks.unusual_flags), so it is the card
    both = [s for s in stations if "near_unanimity" in codes.get(s.key, set())]
    both.sort(key=lambda s: -(s.turnout or 0))

    without = [s for s in stations if controller_of(ctrl.get(s.key), index) == "none"]
    read = sum(1 for s in stations if controller_of(ctrl.get(s.key), index) is not None)
    by_settlement: dict[str, list] = defaultdict(list)
    for s in without:
        by_settlement[settlement_of(s)].append(s)
    without_groups = sorted(by_settlement.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    register = [s for s in stations if "registered_jump" in codes.get(s.key, set())]
    register.sort(key=lambda s: -next((f.data["growth"] for f in flags_of[s.key] if f.code == "registered_jump"), 0))
    apart = [s for s in stations if "turnout_apart" in codes.get(s.key, set())]
    apart.sort(key=lambda s: -abs(next((f.data["now"] - f.data["base"] for f in flags_of[s.key]
                                        if f.code == "turnout_apart"), 0)))

    silent = [s for s in stations if groups.get(s.key, set()) & STANDS_OUT
              and not codes[s.key] & {"remark_filed", "observer_remarks"}
              and not (reviews.get(s.key) and reviews[s.key].remarks)]
    silent.sort(key=lambda s: _num(s.number))
    return {"repeated": repeated, "unanimous": both, "without": without, "without_groups": without_groups,
            "ctrl_read": read, "register": register, "apart": apart, "silent": silent}


def station_json(stations: list, ctrl: dict, flags_of: dict, settlement_of, n_lists: int, hrefs: dict,
                 display=lambda text: text) -> list[dict]:
    """What mun.js needs for every station: votes per list, the valid total, who sits on the board for each list,
    the flag codes, the settlement and the page link."""
    out = []
    for s in stations:
        c = ctrl.get(s.key)
        boards = None if controller_of(c, 1) is None else [controller_of(c, n)[0] for n in range(1, n_lists + 1)]
        out.append({"n": s.number, "name": display(s.name), "set": display(settlement_of(s)), "reg": s.registered,
                    "turnout": round(s.turnout, 4) if s.counted and s.turnout is not None else None,
                    "valid": s.valid if s.counted else None, "v": list(s.votes) if s.counted else None,
                    "ctrl": "".join(boards) if boards else None, "flags": sorted(codes_of(flags_of.get(s.key, []))),
                    "href": hrefs[s.key]})
    return out


def by_settlement(stations: list, settlements: dict, figures: dict, index: int | None) -> list[dict]:
    """The municipality's result settlement by settlement: stations, the census population, registered voters,
    turnout, the leading list with its share of the valid votes (and the runner-up's share, for how close it was),
    and list `index`'s share. Stations not placed in a settlement are one row at the end with an empty name.
    Settlements with the most registered voters first."""
    groups: dict[str, list] = defaultdict(list)
    units: dict[str, tuple] = {}
    for s in stations:
        e = settlements.get(s.key)
        name = e["s"] if e and e.get("s") else ""
        groups[name].append(s)
        if e and e.get("u") and name:
            units[name] = (e["u"], name)
    rows = []
    for name, sts in groups.items():
        counted = [s for s in sts if s.counted]
        reg = sum(s.registered for s in counted)
        voted = sum(s.voted for s in counted)
        valid = sum(s.valid or 0 for s in counted)
        n = max((len(s.votes) for s in counted), default=0)
        votes = [sum(s.votes[i] or 0 for s in counted if i < len(s.votes)) for i in range(n)]
        order = sorted(range(n), key=lambda i: (-votes[i], i)) if valid else []
        f = figures.get(units.get(name)) if name else None
        rows.append({"name": name, "stations": len(sts), "counted": len(counted), "population": f.pop2022 if f else None,
                     "registered": reg, "turnout": voted / reg if reg else None, "valid": valid, "votes": votes,
                     "leader": order[0] if order and votes[order[0]] else None,
                     "share": votes[order[0]] / valid if order and valid else None,
                     "second": votes[order[1]] / valid if len(order) > 1 and valid else None,
                     "mine": votes[index] / valid if index is not None and valid and index < n else None})
    rows.sort(key=lambda r: (r["name"] == "", -r["registered"]))
    return rows


FACT_MIN_REGISTERED = 100  # a settlement smaller than this says little about a list's strength


def facts(rows: list[dict], top: list[int]) -> list[dict]:
    """A few things worth saying about the settlements, for the image people share: the highest and lowest
    turnout, and for each of the lists in `top` (ballot indexes) where it is strongest and weakest. Only placed
    settlements with at least FACT_MIN_REGISTERED registered voters; each fact is {"kind", ...} for the strings."""
    named = [r for r in rows if r["name"] and r["registered"] >= FACT_MIN_REGISTERED and r["valid"]]
    out = []
    if len(named) >= 2:
        hi = max(named, key=lambda r: r["turnout"] or 0)
        lo = min(named, key=lambda r: r["turnout"] or 0)
        if hi is not lo:
            out.append({"kind": "turnout", "hi": hi["name"], "hv": hi["turnout"], "lo": lo["name"], "lv": lo["turnout"]})
        for i in top:
            share = lambda r: (r["votes"][i] if i < len(r["votes"]) else 0) / r["valid"]  # noqa: E731
            hi, lo = max(named, key=share), min(named, key=share)
            if hi is not lo:
                out.append({"kind": "list", "index": i, "hi": hi["name"], "hv": share(hi), "lo": lo["name"], "lv": share(lo)})
    return out


def leaders(rows: list[dict]) -> list[tuple[int, list[str]]]:
    """Which list is first in which settlements: (list index, settlement names), most settlements first; the
    names in the order of the rows (largest settlement first). Unplaced stations are left out."""
    won: dict[int, list[str]] = defaultdict(list)
    for r in rows:
        if r["name"] and r["leader"] is not None:
            won[r["leader"]].append(r["name"])
    return sorted(won.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def codes_of(flags: list) -> set[str]:
    return {f.code for f in flags}


def _num(number: str) -> int:
    return int(number) if number.isdigit() else 0
