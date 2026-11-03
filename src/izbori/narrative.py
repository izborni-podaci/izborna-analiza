"""A few sentences at the top of the pages across elections, written from the numbers by the same rules for every
place and every contestant: invalid ballots and flags first, then turnout and how it compares, then who had most
votes, and last how the place itself changed. The text states numbers and comparisons; it never judges them.

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


def flags(rows: list[Election], loc: str) -> list[str]:
    flagged = [r for r in rows if r.flags]
    if not flagged:
        return [t("an_no_flags", loc)]
    items = "; ".join(f"{r.short} ({', '.join(_flag(c, loc) for c in r.flags)})" for r in flagged)
    out = [t("an_flags", loc, k=len(flagged), n=len(rows), items=items)]
    seen = Counter(c for r in rows for c in set(r.flags))
    same = sorted(((c, m) for c, m in seen.items() if m >= 2), key=lambda x: (-x[1], -BY_CODE[x[0]].weight, x[0]))
    if same:
        out.append(t("an_same", loc, items=", ".join(f"{_flag(c, loc)} ({t('repeat_times', loc, n=m)})"
                                                      for c, m in same)))
    return out


def invalid(rows: list[Election], ref: str, loc: str) -> str | None:
    rs = [r for r in rows if r.invalid is not None and r.ref_invalid is not None]
    if not rs:
        return None
    top = max(rs, key=lambda r: r.invalid)  # the newest when tied
    kw = {"share": fmt_pct(top.invalid, loc), "short": top.short, "label": t(f"an_label_{ref}", loc),
          "ref": fmt_pct(top.ref_invalid, loc), "cmp": t(f"an_cmp_{ref}", loc), "n": len(rs)}
    if len(rs) == 1:
        return t("an_invalid_one", loc, **kw)
    j = sum(1 for r in rs if _higher(r.invalid, r.ref_invalid))
    return t("an_invalid" if j else "an_invalid_never", loc, j=j, **kw)


def turnout(rows: list[Election], ref: str, loc: str) -> str | None:
    rs = [r for r in rows if r.turnout is not None]
    if not rs:
        return None
    now, earlier = rs[0], rs[1:]
    kw = {"t": fmt_pct(now.turnout, loc), "short": now.short, "cmp": t(f"an_cmp_{ref}", loc)}
    if now.ref_turnout is None:
        text = t("an_turnout_plain", loc, **kw)
    elif not _higher(now.turnout, now.ref_turnout) and not _higher(now.ref_turnout, now.turnout):
        text = t("an_turnout_same", loc, **kw)
    else:
        d = now.turnout - now.ref_turnout
        text = t("an_turnout", loc, d=fmt_num(abs(d) * 100, loc), dir=t("an_higher" if d > 0 else "an_lower", loc), **kw)
    if len(earlier) == 1:
        text += "; " + t("an_earlier_one", loc, x=fmt_pct(earlier[0].turnout, loc), short=earlier[0].short)
    elif earlier:
        text += "; " + t("an_earlier_range", loc, lo=fmt_pct(min(r.turnout for r in earlier), loc),
                         hi=fmt_pct(max(r.turnout for r in earlier), loc))
    return text + "."


def registered(rows: list[Election], loc: str) -> str | None:
    rs = [r for r in rows if r.registered]
    if len(rs) < 2:
        return None
    new, old = rs[0], rs[-1]
    return t("an_registered", loc, a=fmt_int(old.registered, loc), first=old.short, b=fmt_int(new.registered, loc),
             last=new.short, change=_signed_pct(new.registered / old.registered - 1, loc))


def leader(rows: list[Election], ref: str, loc: str) -> str | None:
    rs = [r for r in rows if r.leader]
    if not rs:
        return None
    now = rs[0]
    label = short_label(now.leader)
    text = t("an_leader", loc, short=now.short, label=latin(label) if loc == "en" else label,
             share=fmt_pct(now.leader_share, loc), ref_label=t(f"an_label_{ref}", loc),
             ref=fmt_pct(now.ref_leader_share, loc))
    known = [r for r in rs if r.same_leader is not None]
    if len(known) >= 2:
        s = sum(1 for r in known if r.same_leader)
        key = "an_same_leader_all" if s == len(known) else "an_same_leader_none" if s == 0 else "an_same_leader"
        text += "; " + t(key, loc, s=s, n=len(known), cmp=t(f"an_cmp_{ref}", loc))
    return text + "."


def place_changes(rows: list[Election], absent: list[str], loc: str) -> list[str]:
    """Earlier numbers and names, newest first, and the elections the place was not part of."""
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
        out.append(t("an_former", loc, items="; ".join(f"{n} ({', '.join(s)})" for n, s in former.items())))
    if names:
        name, shorts = names[0]
        out.append(t("an_renamed", loc, name=latin(name) if loc == "en" else name, shorts=", ".join(shorts)))
    if not out and len(rows) >= 2:
        out.append(t("an_same_place", loc))
    if absent:
        out.append(t("place_absent", loc, list=", ".join(absent)))
    return out


def rank(rows: list[Election], what: str, peers: str, loc: str) -> str | None:
    """Where the newest election puts this place among its peers (the stations of its municipality, or all
    municipalities), counting from the highest. Left out with fewer than five peers."""
    now = next((r for r in rows if getattr(r, what) is not None), None)
    if now is None or getattr(now, f"rank_{what}") is None:
        return None
    r, n = getattr(now, f"rank_{what}")
    return t(f"an_rank_{what}_{peers}", loc, short=now.short, r=fmt_int(r, loc), n=fmt_int(n, loc))


def place(rows: list[Election], absent: list[str], loc: str) -> list[str]:
    """The paragraphs at the top of a polling place's page. rows: newest election first."""
    paragraphs = [
        [*flags(rows, loc), invalid(rows, "mun", loc), rank(rows, "invalid", "mun", loc)],
        [turnout(rows, "mun", loc), rank(rows, "turnout", "mun", loc), registered(rows, loc)],
        [leader(rows, "mun", loc)],
        place_changes(rows, absent, loc),
    ]
    return [" ".join(s for s in p if s) for p in paragraphs if any(p)]


def municipality(rows: list[Election], absent: list[str], repeat: tuple[int, int],
                 network: tuple[int, int, int], loc: str) -> list[str]:
    """The paragraphs at the top of a municipality's page. rows: newest election first; repeat: its places
    flagged in at least one and in at least two elections; network: places new in its newest election, places no
    longer used, places renumbered."""
    now = rows[0]
    first = [t("an_mun_flags", loc, short=now.short, f=fmt_int(now.flagged, loc), s=fmt_int(now.stations, loc),
               share=fmt_pct(now.flagged / now.stations if now.stations else None, loc),
               overall=fmt_pct(now.ref_flagged, loc))]
    if len(rows) >= 2:
        first.append(t("an_mun_repeat", loc, a=fmt_int(repeat[0], loc), b=fmt_int(repeat[1], loc)))
    first.extend([invalid(rows, "all", loc), rank(rows, "invalid", "all", loc)])
    changes = []
    if len(rows) >= 2:
        old = rows[-1]
        text = t("an_mun_network", loc, a=fmt_int(old.stations, loc), first=old.short, b=fmt_int(now.stations, loc),
                 last=now.short)
        parts = [t(key, loc, n=fmt_int(n, loc)) for key, n in zip(("an_net_new", "an_net_gone", "an_net_renum"), network)
                 if n]
        changes.append(text + ("; " + ", ".join(parts) if parts else "") + ".")
    if absent:
        changes.append(t("mun_absent", loc, list=", ".join(absent)))
    paragraphs = [first, [turnout(rows, "all", loc), rank(rows, "turnout", "all", loc), registered(rows, loc)],
                  [leader(rows, "all", loc)], changes]
    return [" ".join(s for s in p if s) for p in paragraphs if any(p)]
