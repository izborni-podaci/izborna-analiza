"""Station checks. Every check treats every contestant the same way; none looks at who gains.

Three groups:
- paper:   the station's own numbers don't add up (strongest signals)
- change:  the archive shows numbers, minutes or corrections changing after publication
- unusual: lopsided or shifting results; often legitimate, so they weigh least
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median

from izbori.history import is_number_field
from izbori.model import Round, Station


@dataclass(frozen=True)
class Check:
    code: str
    group: str
    weight: float


CHECKS = [
    Check("ballots_over_signed", "paper", 5),
    Check("sum_mismatch", "paper", 3),
    Check("ballot_mismatch", "paper", 3),
    Check("signed_over_ballots", "paper", 3),
    Check("signed_over_registered", "paper", 3),
    Check("full_turnout_typo", "paper", 2),
    Check("correction_still_odd", "paper", 3),
    Check("changed", "change", 3),
    Check("minutes_replaced", "change", 2),
    Check("correction_unapplied", "change", 3),
    Check("invalid_spike", "unusual", 2),
    Check("turnout_jump", "unusual", 2),
    Check("turnout_drop", "unusual", 1),
    Check("near_unanimity", "unusual", 1),
    Check("high_turnout", "unusual", 1),
]
BY_CODE = {c.code: c for c in CHECKS}
GROUPS = ["paper", "change", "unusual"]

# Starting values, documented on the site. Tune on real data, never per contestant.
RULES = {
    "signed_over_ballots_min": 3,  # a voter walking out with a ballot is common; 3 or more is worth a look
    "typo_min_registered": 10,
    "typo_median_below": 0.80,
    "min_registered": 50,
    "high_turnout": 0.90,
    "near_share": 0.80,
    "invalid_abs_share": 0.08,
    "invalid_abs_min_voted": 100,
    "invalid_rel_factor": 3.0,
    "invalid_rel_min": 10,
    "invalid_rel_share": 0.04,
    "turnout_jump": 0.25,
    "jump_min_registered": 100,
}

ARITHMETIC = {"sum_mismatch", "ballot_mismatch", "ballots_over_signed", "signed_over_ballots",
              "signed_over_registered", "full_turnout_typo"}


@dataclass
class Flag:
    station: str
    code: str
    data: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.station}:{self.code}"

    @property
    def check(self) -> Check:
        return BY_CODE[self.code]


def _address(s: Station) -> tuple[str, str]:
    name = s.name.upper()
    for q in '"„“”\'«»':
        name = name.replace(q, "")
    return s.municipality_code, " ".join(name.split())


def _median_excluding(stations: list[Station], me: Station, value) -> float | None:
    vals = [value(t) for t in stations if t is not me]
    vals = [v for v in vals if v is not None]
    return median(vals) if vals else None


def paper_flags(s: Station, mun_peers: list[Station]) -> list[Flag]:
    out = []
    if s.valid is not None:
        total = sum(v or 0 for v in s.votes)
        if total != s.valid:
            out.append(Flag(s.key, "sum_mismatch", {"sum": total, "valid": s.valid}))
    if None not in (s.valid, s.invalid, s.ballots) and s.valid + s.invalid != s.ballots:
        out.append(Flag(s.key, "ballot_mismatch", {"valid": s.valid, "invalid": s.invalid, "ballots": s.ballots}))
    if s.ballots is not None and s.voted is not None:
        if s.ballots > s.voted:
            out.append(Flag(s.key, "ballots_over_signed",
                            {"ballots": s.ballots, "voted": s.voted, "diff": s.ballots - s.voted}))
        elif s.voted - s.ballots >= RULES["signed_over_ballots_min"]:
            out.append(Flag(s.key, "signed_over_ballots",
                            {"voted": s.voted, "ballots": s.ballots, "diff": s.voted - s.ballots}))
    if s.voted is not None and s.registered is not None and s.voted > s.registered:
        out.append(Flag(s.key, "signed_over_registered",
                        {"voted": s.voted, "registered": s.registered, "diff": s.voted - s.registered}))
    if (s.kind == "domestic" and s.registered is not None and s.registered >= RULES["typo_min_registered"]
            and s.voted == s.registered):
        med = _median_excluding(mun_peers, s, lambda t: t.turnout)
        if med is not None and med < RULES["typo_median_below"]:
            out.append(Flag(s.key, "full_turnout_typo", {"registered": s.registered, "voted": s.voted, "median": med}))
    if s.correction_url and any(f.code in ARITHMETIC for f in out):
        out.append(Flag(s.key, "correction_still_odd", {"form": s.correction_form}))
    return out


def unusual_flags(s: Station, mun_peers: list[Station], addr_peers: list[Station], typo: bool) -> list[Flag]:
    out = []
    t = s.turnout
    if not typo and t is not None and s.registered >= RULES["min_registered"] and t >= RULES["high_turnout"]:
        top = max(range(len(s.votes)), key=lambda i: s.votes[i] or 0) if s.votes else None
        share = (s.votes[top] or 0) / s.valid if top is not None and s.valid else 0
        if share >= RULES["near_share"]:
            out.append(Flag(s.key, "near_unanimity", {"turnout": t, "contestant": top + 1, "share": share,
                                                      "registered": s.registered}))
        else:
            out.append(Flag(s.key, "high_turnout", {"turnout": t, "registered": s.registered}))
    share = s.invalid_share
    if share is not None and s.invalid is not None:
        if (s.voted or 0) >= RULES["invalid_abs_min_voted"] and share >= RULES["invalid_abs_share"]:
            out.append(Flag(s.key, "invalid_spike", {"invalid": s.invalid, "share": share, "basis": "absolute"}))
        elif s.invalid >= RULES["invalid_rel_min"] and share >= RULES["invalid_rel_share"]:
            peers, basis = [p for p in addr_peers if p is not s], "address"
            if not peers:
                peers, basis = [p for p in mun_peers if p is not s], "municipality"
            shares = [p.invalid_share for p in peers if p.invalid_share is not None]
            if shares:
                med = median(shares)
                if share >= RULES["invalid_rel_factor"] * max(med, 0.005):
                    out.append(Flag(s.key, "invalid_spike",
                                    {"invalid": s.invalid, "share": share, "median": med, "basis": basis}))
    return out


def change_flags(changes: list[dict], stations: dict[str, Station]) -> list[Flag]:
    out = []
    by_station: dict[str, list[dict]] = defaultdict(list)
    for e in changes:
        by_station[e["s"]].append(e)
    for key, events in by_station.items():
        numbers = [e for e in events if is_number_field(e["f"])]
        if numbers:
            first: dict[str, str] = {}
            last: dict[str, str] = {}
            for e in numbers:
                first.setdefault(e["f"], e["o"])
                last[e["f"]] = e["n"]
            out.append(Flag(key, "changed", {"fields": sorted(first), "first": first, "now": last,
                                             "times": sorted({e["t"] for e in numbers})}))
        replaced = [e for e in events if e["f"] == "zapisnik_link" and e["o"] and e["n"] != e["o"]]
        if replaced:
            out.append(Flag(key, "minutes_replaced", {"count": len(replaced), "last": replaced[-1]["t"]}))
        corrections = [e for e in events if e["f"] == "korekcija_dokument_link" and e["n"]]
        if corrections:
            appeared = corrections[0]["t"]
            if not any(e["t"] >= appeared for e in numbers):
                st = stations.get(key)
                out.append(Flag(key, "correction_unapplied",
                                {"appeared": appeared, "form": st.correction_form if st else ""}))
    return out


GENERIC = {"OSNOVNA", "SKOLA", "DOM", "KULTURE", "MESNA", "ZAJEDNICA", "SALA", "ZGRADA", "PROSTORIJE", "BROJ",
           "UCIONICA", "HOL", "SREDNJA", "OPSTINE", "SKUPSTINA", "OBDANISTE", "VRTIC", "DECJI"}


def history_flags(rnd: Round, previous: list[Round], links=None) -> list[Flag]:
    """Turnout at a station compared with the same place in the last earlier round that has it (same kind of
    election first). The place is followed by address, name and number (places.py), so a renumbered station is
    still compared with itself and a new station on an old number is not. The baseline is the median change at the
    municipality's other stations, so regional swings and a different kind of election don't count. Registered
    voters are compared per municipality instead (see stats.register_changes): station areas are redrawn between
    elections, which moves voters around.

    links: the places across these rounds (report.analyze passes them with addresses and manual corrections);
    without them, the rounds are followed by name and number alone, taking `previous` newest first."""
    if links is None:
        from izbori.places import follow
        links = follow([(r.id, r.stations, {}) for r in reversed(previous)] + [(rnd.id, rnd.stations, {})])
    pairs = []
    for s in rnd.stations:
        if not (s.counted and s.kind == "domestic"):
            continue
        place = links.of(rnd.id, s.key)
        for prev in previous:
            p = place.stations.get(prev.id) if place else None
            if p is None or not (p.counted and p.kind == "domestic"):
                continue
            if s.registered >= RULES["jump_min_registered"] and p.registered >= RULES["jump_min_registered"]:
                pairs.append((s, p, prev))
            break
    by_mun: dict[tuple, list[float]] = defaultdict(list)
    by_round: dict[str, list[float]] = defaultdict(list)
    for s, p, prev in pairs:
        by_mun[(prev.id, s.municipality_code)].append(s.turnout - p.turnout)
        by_round[prev.id].append(s.turnout - p.turnout)
    out = []
    for s, p, prev in pairs:
        local = by_mun[(prev.id, s.municipality_code)]
        base = median(local) if len(local) >= 5 else median(by_round[prev.id])
        shift = (s.turnout - p.turnout) - base
        if abs(shift) >= RULES["turnout_jump"]:
            code = "turnout_jump" if shift > 0 else "turnout_drop"
            out.append(Flag(s.key, code, {"before": p.turnout, "now": s.turnout, "base": base, "round": prev.id}))
    return out


def station_flags(rnd: Round, changes: list[dict] | None = None, previous: list[Round] | None = None,
                  links=None) -> list[Flag]:
    counted = [s for s in rnd.stations if s.counted]
    by_mun: dict[str, list[Station]] = defaultdict(list)
    by_addr: dict[tuple, list[Station]] = defaultdict(list)
    for s in counted:
        if s.kind == "domestic":
            by_mun[s.municipality_code].append(s)
            by_addr[_address(s)].append(s)
    flags: list[Flag] = []
    for s in counted:
        own = paper_flags(s, by_mun[s.municipality_code])
        flags.extend(own)
        if s.kind == "domestic":
            typo = any(f.code == "full_turnout_typo" for f in own)
            flags.extend(unusual_flags(s, by_mun[s.municipality_code], by_addr[_address(s)], typo))
    if changes:
        flags.extend(change_flags(changes, {s.key: s for s in rnd.stations}))
    if previous:
        flags.extend(history_flags(rnd, previous, links))
    order = {c.code: i for i, c in enumerate(CHECKS)}
    flags.sort(key=lambda f: (f.station, order[f.code]))
    return flags


def group_by_station(flags: list[Flag]) -> dict[str, list[Flag]]:
    out: dict[str, list[Flag]] = defaultdict(list)
    for f in flags:
        out[f.station].append(f)
    return dict(out)


def score(flags: list[Flag]) -> float:
    return sum(f.check.weight for f in flags)
