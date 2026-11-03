"""The short rows at the top of the pages across elections ("In short"), written from the numbers by the same
rules for every place and every contestant: flags and invalid ballots first, then turnout and how it compares, then
who had most votes, how the place itself changed, and the observers' records. Each row has a label and a line or
two of short facts, the main one first; the numbers are the latest election's unless the line names another. The
text states numbers and comparisons; it never judges them.

A place is compared with its municipality in the same election, a municipality with the whole election (the
country, Vojvodina for provincial elections, the city for local ones)."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from izbori.checks import BY_CODE
from izbori.i18n import check_name, fmt_int, fmt_num, fmt_pct, t
from izbori.translit import latin

LABEL_MAX = 48  # characters of a contestant's name in a sentence; the tables keep the full names


@dataclass
class Election:
    """One election at a place or in a municipality, and the same numbers for the area it is compared with."""
    short: str
    registered: int | None = None
    turnout: float | None = None
    invalid: float | None = None  # share of ballots
    flags: list[str] = field(default_factory=list)  # check codes, strongest first
    leader: str = ""  # contestant with most votes here
    leader_share: float | None = None  # its share of valid votes here
    ref_turnout: float | None = None
    ref_invalid: float | None = None
    ref_leader_share: float | None = None  # the same contestant's share in the area compared with
    same_leader: bool | None = None  # whether it had most votes there too
    number: str = ""
    name: str = ""
    stations: int = 0  # for a municipality: its polling stations in that election
    flagged: int = 0  # for a municipality: stations flagged
    ref_flagged: float | None = None  # for a municipality: share of stations flagged in the whole election
    observers: bool | None = None  # whether RIK published an observers' record (form RG-11); None when not known
    observed: int | None = None  # for a municipality: its stations with an observers' record; None when not known
    rank_invalid: tuple[int, int] | None = None  # (rank from the highest, out of how many) among its peers
    rank_turnout: tuple[int, int] | None = None


def short_label(label: str) -> str:
    """A contestant's name short enough for a sentence: what precedes an opening bracket, cut at a word boundary
    after LABEL_MAX characters. The same rule for every contestant."""
    head = label.split(" (")[0].strip() or label
    if len(head) <= LABEL_MAX:
        return head
    return head[:LABEL_MAX].rsplit(" ", 1)[0].rstrip(" -–—,") + "…"


def _same_name(a: str, b: str) -> bool:
    """Names that differ only in quotes, spaces, dashes, case or script."""
    def letters(s: str) -> str:
        s = unicodedata.normalize("NFD", latin(s).upper().replace("Đ", "DJ"))
        return re.sub(r"[^A-Z0-9]", "", "".join(ch for ch in s if not unicodedata.combining(ch)))
    return letters(a) == letters(b)


def _flag(code: str, loc: str) -> str:
    name = check_name(code, loc)
    return name[:1].lower() + name[1:]


def _signed_pct(x: float, loc: str) -> str:
    return ("+" if round(x, 3) > 0 else "−" if round(x, 3) < 0 else "") + fmt_pct(abs(x), loc)


def _higher(a: float, b: float) -> bool:
    """Higher once both are rounded to a tenth of a percent, as the page shows them."""
    return round(a * 1000) > round(b * 1000)


SEP = " · "


@dataclass
class Row:
    label: str
    lines: list[str]


@dataclass
class Summary:
    """What the "In short" section shows: which election and comparison the numbers are for, then the rows."""
    context: str
    rows: list[Row]


def _join(*parts: str | None) -> str:
    return SEP.join(p for p in parts if p)


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _when(r: Election, rows: list[Election]) -> str:
    """The election a figure comes from, named only when it isn't the latest one."""
    return f" ({r.short})" if r is not rows[0] else ""


def _rank(r: Election, what: str, peers: str, loc: str) -> str | None:
    """Where the election puts this place among its peers (the stations of its municipality, or all
    municipalities), counting from the highest; None with fewer than five peers."""
    got = getattr(r, f"rank_{what}")
    return t(f"ar_rank_{what}_{peers}", loc, r=fmt_int(got[0], loc), n=fmt_int(got[1], loc)) if got else None


def flags(rows: list[Election], loc: str) -> list[str]:
    flagged = [r for r in rows if r.flags]
    if not flagged:
        return [t("ar_no_flags_one" if len(rows) == 1 else "ar_no_flags", loc, n=len(rows))]
    if len(rows) == 1:
        out = [_cap(", ".join(_flag(c, loc) for c in rows[0].flags))]
    else:
        items = "; ".join(f"{r.short} ({', '.join(_flag(c, loc) for c in r.flags)})" for r in flagged)
        out = [t("ar_flags", loc, k=len(flagged), n=len(rows), items=items)]
    seen = Counter(c for r in rows for c in set(r.flags))
    same = sorted(((c, m) for c, m in seen.items() if m >= 2), key=lambda x: (-x[1], -BY_CODE[x[0]].weight, x[0]))
    if same:
        out.append(_cap(t("ar_same", loc, items=", ".join(f"{_flag(c, loc)} ({t('repeat_times', loc, n=m)})"
                                                          for c, m in same))))
    return out


def invalid(rows: list[Election], ref: str, loc: str) -> str | None:
    """The latest share of invalid ballots against the area, its rank, and how often it was higher."""
    rs = [r for r in rows if r.invalid is not None and r.ref_invalid is not None]
    if not rs:
        return None
    now = rs[0]
    head = t("ar_invalid", loc, share=fmt_pct(now.invalid, loc), label=t(f"an_label_{ref}", loc),
             ref=fmt_pct(now.ref_invalid, loc)) + _when(now, rows)
    history = None
    if len(rs) >= 2:
        j = sum(1 for r in rs if _higher(r.invalid, r.ref_invalid))
        cmp = t(f"an_cmp_{ref}", loc)
        history = t("ar_invalid_above", loc, j=j, n=len(rs), cmp=cmp) if j else t("ar_invalid_never", loc, cmp=cmp)
    return _cap(_join(head, _rank(now, "invalid", ref, loc), history))


def turnout(rows: list[Election], ref: str, loc: str) -> list[str]:
    rs = [r for r in rows if r.turnout is not None]
    if not rs:
        return []
    now, earlier = rs[0], rs[1:]
    cmp = t(f"an_cmp_{ref}", loc)
    if now.ref_turnout is None:
        against = None
    elif not _higher(now.turnout, now.ref_turnout) and not _higher(now.ref_turnout, now.turnout):
        against = t("ar_turnout_same", loc, cmp=cmp)
    else:
        d = now.turnout - now.ref_turnout
        against = t("ar_turnout_diff", loc, d=fmt_num(abs(d) * 100, loc), dir=t("an_higher" if d > 0 else "an_lower", loc),
                    cmp=cmp)
    lines = [_join(fmt_pct(now.turnout, loc) + _when(now, rows), against)]
    before = None
    if len(earlier) == 1:
        before = t("ar_earlier_one", loc, x=fmt_pct(earlier[0].turnout, loc), short=earlier[0].short)
    elif earlier:
        before = t("ar_earlier_range", loc, lo=fmt_num(100 * min(r.turnout for r in earlier), loc),
                   hi=fmt_pct(max(r.turnout for r in earlier), loc))
    second = _join(_rank(now, "turnout", ref, loc), before)
    return lines + ([_cap(second)] if second else [])


def registered(rows: list[Election], loc: str) -> str | None:
    rs = [r for r in rows if r.registered]
    if len(rs) < 2:
        return None
    new, old = rs[0], rs[-1]
    return t("ar_registered", loc, a=fmt_int(old.registered, loc), first=old.short, b=fmt_int(new.registered, loc),
             change=_signed_pct(new.registered / old.registered - 1, loc))


def leader(rows: list[Election], ref: str, loc: str) -> list[str]:
    rs = [r for r in rows if r.leader]
    if not rs:
        return []
    now = rs[0]
    label = short_label(now.leader)
    lines = [t("ar_leader", loc, label=latin(label) if loc == "en" else label, share=fmt_pct(now.leader_share, loc),
               ref_label=t(f"an_label_{ref}", loc), ref=fmt_pct(now.ref_leader_share, loc)) + _when(now, rows)]
    known = [r for r in rs if r.same_leader is not None]
    if len(known) >= 2:
        s = sum(1 for r in known if r.same_leader)
        key = "ar_same_leader_all" if s == len(known) else "ar_same_leader_none" if s == 0 else "ar_same_leader"
        lines.append(_cap(t(key, loc, s=s, n=len(known), cmp=t(f"an_cmp_{ref}", loc))))
    return lines


def place_changes(rows: list[Election], absent: list[str], loc: str) -> list[str]:
    """Earlier numbers and names, newest first; the registered voters then and now; the elections the place was
    not part of."""
    now, out = rows[0], []
    former: dict[str, list[str]] = {}
    names: list[tuple[str, list[str]]] = []
    for r in rows[1:]:
        if r.number != now.number:
            former.setdefault(r.number, []).append(r.short)
        if r.name and now.name and not _same_name(r.name, now.name):
            hit = next((x for x in names if _same_name(x[0], r.name)), None)
            if hit:
                hit[1].append(r.short)
            else:
                names.append((r.name, [r.short]))
    if former:
        out.append(t("ar_former", loc, items="; ".join(f"{n} ({', '.join(s)})" for n, s in former.items())))
    if names:
        name, shorts = names[0]
        out.append(t("ar_renamed", loc, name=latin(name) if loc == "en" else name, shorts=", ".join(shorts)))
    if not out and len(rows) >= 2:
        out.append(t("ar_same_place", loc))
    reg = registered(rows, loc)
    return out + [_cap(x) for x in (reg, t("ar_absent", loc, list=", ".join(absent)) if absent else None) if x]


def observers(rows: list[Election], loc: str) -> list[str]:
    """In which elections RIK published an observers' record for the station, among those whose documents are known."""
    known = [r for r in rows if r.observers is not None]
    if not known:
        return []
    seen = [r.short for r in known if r.observers]
    if len(known) == 1:
        return [t("ar_observers_one" if seen else "ar_observers_none_one", loc)]
    if not seen:
        return [t("ar_observers_none", loc, n=len(known))]
    missing = [r.short for r in known if not r.observers]
    return [_join(t("ar_observers", loc, k=len(seen), n=len(known)),
                  t("ar_observers_missing", loc, items=", ".join(missing)) if missing else None)]


def mun_observers(rows: list[Election], loc: str) -> list[str]:
    now = next((r for r in rows if r.observed is not None), None)
    if now is None or not now.stations:
        return []
    return [t("ar_mun_records", loc, o=fmt_int(now.observed, loc), s=fmt_int(now.stations, loc)) + _when(now, rows)]


def _summary(context: str, rows: list[tuple[str, list[str | None]]], loc: str) -> Summary:
    return Summary(context, [Row(t(label, loc), [x for x in lines if x]) for label, lines in rows
                             if any(lines)])


def place(rows: list[Election], absent: list[str], loc: str) -> Summary:
    """The rows at the top of a polling place's page. rows: newest election first."""
    return _summary(t("ar_context_mun", loc, short=rows[0].short), [
        ("ar_flags_label", [*flags(rows, loc), invalid(rows, "mun", loc)]),
        ("ar_turnout_label", turnout(rows, "mun", loc)),
        ("ar_leader_label", leader(rows, "mun", loc)),
        ("ar_place_label", place_changes(rows, absent, loc)),
        ("ar_records_label", observers(rows, loc)),
    ], loc)


def municipality(rows: list[Election], absent: list[str], repeat: tuple[int, int],
                 network: tuple[int, int, int], loc: str) -> Summary:
    """The rows at the top of a municipality's page. rows: newest election first; repeat: its places flagged in
    at least one and in at least two elections; network: places new in its newest election, places no longer
    used, places renumbered."""
    now = rows[0]
    flagged = [t("ar_mun_flags", loc, f=fmt_int(now.flagged, loc), s=fmt_int(now.stations, loc),
                 share=fmt_pct(now.flagged / now.stations if now.stations else None, loc),
                 overall=fmt_pct(now.ref_flagged, loc))]
    if len(rows) >= 2:
        flagged.append(_cap(t("ar_mun_repeat", loc, a=fmt_int(repeat[0], loc), b=fmt_int(repeat[1], loc))))
    flagged.append(invalid(rows, "all", loc))
    stations = []
    if len(rows) >= 2:
        old = rows[-1]
        parts = [t(key, loc, n=fmt_int(n, loc)) for key, n in zip(("ar_net_new", "ar_net_gone", "ar_net_renum"),
                                                                    network) if n]
        stations.append(_join(t("ar_mun_network", loc, a=fmt_int(old.stations, loc), first=old.short,
                                b=fmt_int(now.stations, loc)), *parts))
    reg = registered(rows, loc)
    stations += [_cap(x) for x in (reg, t("ar_mun_absent", loc, list=", ".join(absent)) if absent else None) if x]
    return _summary(t("ar_context_all", loc, short=now.short), [
        ("ar_flags_label", flagged),
        ("ar_turnout_label", turnout(rows, "all", loc)),
        ("ar_leader_label", leader(rows, "all", loc)),
        ("ar_stations_label", stations),
        ("ar_records_label", mun_observers(rows, loc)),
    ], loc)
