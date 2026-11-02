"""Polling stations and municipalities flagged again and again, across every archived election.

A station is recognised by municipality and number. Station areas and addresses change between elections, so a
row also notes the elections in which the station's name clearly differs from its newest one."""

from __future__ import annotations

from collections import Counter, defaultdict

from izbori.checks import BY_CODE, same_place
from izbori.targets import DECAY

TWICE = 2.0  # a municipality stands out in an election when its share of stations to check is at least this × national


def stations(analyses: list) -> tuple[list[dict], int]:
    """Every station flagged in at least one election, most elections first, then by score; and how many were
    flagged in only one. analyses: oldest election first."""
    rows: dict[str, dict] = {}
    for age, a in enumerate(reversed(analyses)):
        weight = DECAY ** age
        rid = a.round.id
        for s in a.round.stations:
            row = rows.get(s.key)
            if row is None:
                row = rows[s.key] = {"key": s.key, "station": s, "rid": rid, "took": set(), "flags": {},
                                     "score": 0.0, "renamed": set()}
            elif s.name and row["station"].name and not same_place(row["station"], s):
                row["renamed"].add(rid)
            row["took"].add(rid)
        for key, flags in a.by_station.items():
            row = rows.get(key)
            if row is None:
                continue
            codes = sorted({f.code for f in flags}, key=lambda c: -BY_CODE[c].weight)
            row["flags"][rid] = codes
            row["score"] += weight * sum(f.check.weight for f in flags)
    out, once = [], 0
    for row in rows.values():
        k = len(row["flags"])
        if k == 0:
            continue
        once += k == 1
        seen = Counter(c for codes in row["flags"].values() for c in codes)
        same = sorted(((c, m) for c, m in seen.items() if m >= 2), key=lambda x: (-x[1], -BY_CODE[x[0]].weight))
        row.update({"k": k, "n": len(row["took"]), "types": " ".join(sorted(seen)), "same": same,
                    "same_codes": " ".join(c for c, _ in same)})
        out.append(row)
    out.sort(key=lambda r: (-r["k"], -r["score"], r["key"]))
    return out, once


def same_counts(rows: list[dict]) -> list[tuple[str, int]]:
    """For each check: at how many stations it came up in two or more elections."""
    c = Counter(code for r in rows for code, _ in r["same"])
    return sorted(c.items(), key=lambda x: (-x[1], x[0]))


def municipalities(analyses: list) -> tuple[list[dict], dict[str, float]]:
    """Municipalities whose share of stations to check was at least twice the national share in most of the
    elections they took part in (and at least two); with the national share per election."""
    national: dict[str, float] = {}
    cells: dict[str, dict[str, dict]] = defaultdict(dict)
    names: dict[str, str] = {}
    for a in analyses:
        rid = a.round.id
        total = len(a.round.stations)
        national[rid] = len(a.by_station) / total if total else 0.0
        by_mun: dict[str, list] = defaultdict(list)
        for s in a.round.stations:
            by_mun[s.municipality_code].append(s)
            names[s.municipality_code] = s.municipality
        for code, sts in by_mun.items():
            flagged = sum(1 for s in sts if s.key in a.by_station)
            share = flagged / len(sts)
            cells[code][rid] = {"share": share, "flagged": flagged, "stations": len(sts),
                                "above": len(sts) >= 5 and national[rid] > 0 and share >= TWICE * national[rid]}
    out = []
    for code, by_round in cells.items():
        n = len(by_round)
        above = sum(1 for c in by_round.values() if c["above"])
        if n >= 2 and above >= 2 and above * 2 > n:
            ratio = sum(c["share"] / national[r] for r, c in by_round.items() if national[r]) / n
            out.append({"code": code, "name": names[code], "cells": by_round, "n": n, "above": above,
                        "ratio": ratio})
    out.sort(key=lambda m: (-m["above"], -m["ratio"]))
    return out, national
