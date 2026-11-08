"""What stands out in the latest election: the four cards on the home page.

Each card is one rule, applied to every contestant or every municipality alike; nothing names a list in advance.

- gap: the contestant whose share differs most between the smallest settlements (under 500 people) and the largest
  cities (100,000 or more), from the election's page by kind of settlement.
- flagged: the municipality with the largest share of flagged polling stations (at least MIN_STATIONS stations, in
  the country), and the two after it.
- repeated: the places flagged in every election they took part in, among those in at least three elections, by
  municipality.
- top: the three contestants with most votes in the country, each with the municipality where its share is largest
  and the one where it is smallest (municipalities in the country with at least MIN_STATIONS counted stations).

A card the data can't fill (no census, one election, fewer than three contestants) is left out, not guessed."""

from __future__ import annotations

from collections import Counter

MIN_STATIONS = 10
SMALL, LARGE = 0, 4  # the classes of bysettlement.SIZE: under 500, 100,000 or more


def gap(rows: list[dict]) -> dict | None:
    """The contestant whose share of the valid votes differs most between the smallest and the largest settlements."""
    best = None
    for r in rows:
        shares = r["votes"].get("size") or []
        if len(shares) <= LARGE or shares[SMALL] is None or shares[LARGE] is None:
            continue
        d = abs(shares[SMALL] - shares[LARGE])
        if best is None or d > best["diff"]:
            best = {"number": r["number"], "label": r["label"], "small": shares[SMALL], "large": shares[LARGE],
                    "diff": d}
    return best


def flagged(muns: list[dict]) -> list[dict]:
    """Municipalities in the country by the share of their stations with a flag, largest first; the first three."""
    rows = [m for m in muns if m["kind"] == "domestic" and m["stations"] >= MIN_STATIONS and m["flagged"]]
    rows.sort(key=lambda m: (-m["flagged"] / m["stations"], -m["flagged"], m["name"]))
    return [{"code": m["code"], "name": m["name"], "flagged": m["flagged"], "stations": m["stations"]}
            for m in rows[:3]]


def repeated(places: list, flagged_in: dict[str, set], names: dict[str, str], at_least: int = 3) -> dict | None:
    """Places with a flag in every election they took part in, among those in at least `at_least` elections (the
    provincial and the Belgrade elections cover only parts of the country): how many, how many elections the fewest
    of them took part in, and their municipalities (most first)."""
    hits = [p for p in places if len(p.rounds) >= at_least
            and all(p.stations[rid].key in flagged_in.get(rid, {}) for rid in p.rounds)]
    if not hits:
        return None
    by_mun = Counter(p.code for p in hits)
    return {"n": len(hits), "elections": min(len(p.rounds) for p in hits),
            "municipalities": [{"code": c, "name": names.get(c, c), "n": n} for c, n in by_mun.most_common()]}


def top(contestants: list, labels: list[str], muns: list[dict], votes: dict[str, list]) -> list[dict]:
    """The three contestants with most votes, each with its strongest and weakest municipality by share."""
    n = len(contestants)
    total = [0] * n
    for code, vs in votes.items():
        for i in range(min(n, len(vs))):
            total[i] += vs[i] or 0
    order = sorted(range(n), key=lambda i: (-total[i], contestants[i].number))[:3]
    usable = [m for m in muns if m["kind"] == "domestic" and m["counted"] >= MIN_STATIONS
              and sum(v or 0 for v in votes.get(m["code"], [])) > 0]
    out = []
    for i in order:
        shares = []
        for m in usable:
            vs = votes[m["code"]]
            valid = sum(v or 0 for v in vs)
            shares.append((((vs[i] if i < len(vs) else 0) or 0) / valid, m))
        if not shares:
            continue
        hi = max(shares, key=lambda x: x[0])
        lo = min(shares, key=lambda x: x[0])
        out.append({"number": contestants[i].number, "label": labels[i], "votes": total[i],
                    "best": {"code": hi[1]["code"], "name": hi[1]["name"], "share": hi[0]},
                    "worst": {"code": lo[1]["code"], "name": lo[1]["name"], "share": lo[0]}})
    return out if len(out) == 3 else []
