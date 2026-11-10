"""A city settlement by its quarters: which quarter each of its polling stations is in (9 Nov 2026).

`data/geo/quarters.json` (izbori geo --quarters) holds, per municipality, a settlement drawn by its quarters
(OpenStreetMap's place=quarter …) and the names of the public buildings inside it with the quarter each stands in.
A station in that settlement is placed in a quarter by its building: the name in quotes in RIK's station name
(ОШ "ВЕЉКО ПЕТРОВИЋ" → Вељко Петровић) is looked for among the buildings of the same kind (a school among schools),
and a local community's hall (МЗ "АДИЦЕ") also by the quarter of that name. A name found in more than one quarter,
or nowhere, places nothing: the station stays in the settlement, shown apart from the quarters. A named place
inside a quarter (a neighbourhood OpenStreetMap draws within it: Сајлово, Шангај) is among the names too, so a local
community named for it finds its quarter.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from izbori.settlements import norm

FILE = "quarters.json"
# a quarter OpenStreetMap names by its official name, shown by the name people use (Bistrica is Novo naselje)
SPOKEN = {"Бистрица": "Ново насеље"}
# what kind of building a name speaks of, by the words it starts with or holds (compared in norm's form)
KINDS = (
    ("school", ("OS", "OSNOVNA", "SKOLA", "GIMNAZIJA", "SSC", "SS", "SREDNJA", "TEHNICKA", "MEDICINSKA", "MUZICKA")),
    ("community", ("MZ", "MESNA", "ZAJEDNICA")),
    ("kindergarten", ("PU", "PREDSKOLSKA", "VRTIC", "OBJEKAT")),
)
GENERIC = {"OS", "OSNOVNA", "SKOLA", "MZ", "MESNA", "ZAJEDNICA", "PU", "PREDSKOLSKA", "USTANOVA", "VRTIC", "OBJEKAT",
           "DOM", "SALA", "VELIKA", "MALA", "KANCELARIJA", "ZGRADA", "UPRAVNA", "SREDNJA", "SS", "SSC", "ZA", "I", "U",
           "NA", "DJECIJI", "DECIJI", "CENTAR", "KLUB", "PROSTORIJE", "ULAZ"}


def load(root: Path) -> dict:
    p = Path(root) / "geo" / FILE
    return json.loads(p.read_text(encoding="utf-8")).get("areas", {}) if p.exists() else {}


def names(area: dict) -> tuple[str, str]:
    """The whole municipality's name and its city settlement's: ("Општина Нови Сад", "Град Нови Сад")."""
    city = area.get("settlement", "")
    return f"Општина {city}", f"Град {city}"


def kind_of(name: str) -> str | None:
    w = norm(name).split()
    for kind, marks in KINDS:
        if any(m in w for m in marks):
            return kind
    return None


def distinct(text: str) -> frozenset[str]:
    return frozenset(w for w in norm(text).split() if w not in GENERIC)


def place(stations: list, settlement_of, area: dict) -> dict[str, str]:
    """Station key → quarter, for the stations in the area's settlement whose building is found in one quarter."""
    city = area.get("settlement", "")
    quarters = {norm(f["properties"]["name"]): f["properties"]["name"] for f in area.get("features", [])}
    points = [(kind_of(n), distinct(n), q, n) for n, q in area.get("points", [])]
    out = {}
    for s in stations:
        if settlement_of(s) != city:
            continue
        q = quarter_of(s.name, points, quarters)
        if q:
            out[s.key] = SPOKEN.get(q, q)
    return out


def quarter_of(name: str, points: list, quarters: dict[str, str]) -> str | None:
    """The quarter of a station's building, or None. Among the buildings bearing the station's name, those that
    share most of the words outside the quotes (ОШ, ГИМНАЗИЈА, КУД, СРЕДЊА …) are taken: a primary school's station
    finds the primary school, not the secondary school of the same name; a name still in two quarters is left."""
    kind = kind_of(name)
    quoted = re.findall(r'"([^"]+)"', name or "")
    parts = quoted or [name or ""]
    outside = set(norm(re.sub(r'"[^"]+"', " ", name or "")).split()) - {"I"}
    for part in reversed(parts):  # ПУ "РАДОСНО ДЕТИЊСТВО" - ОБЈЕКАТ "МРВИЦА": the last name is the building's
        want = distinct(part)
        if not want:
            continue
        if kind == "community":  # a local community's hall: the quarter of its name (МЗ "ЈУЖНИ ТЕЛЕП" → Телеп)
            named = {v for k, v in quarters.items() if set(k.split()) <= want}
            if len(named) == 1:
                return named.pop()
        hits = [(len(outside & set(norm(full).split())), q)
                for k, have, q, full in points
                if (kind is None or k is None or k == kind)
                and (have == want or (want < have and (len(want) > 1 or k == kind))
                     # a name with nothing in quotes holds the building's whole name and more ("ГРАДСКА УПРАВА ЗА
                     # ИНСПЕКЦИЈСКЕ ПОСЛОВЕ ГРАДА НОВОГ САДА"): a building of three words or more inside it
                     or (not quoted and len(have) >= 3 and have < want))]
        if not hits:
            continue
        best = max(h for h, _ in hits)
        found = {q for h, q in hits if h == best}
        return found.pop() if len(found) == 1 else None  # the same name in two quarters: not guessed
    return None
