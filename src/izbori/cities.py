"""Cities that RIK's results split into several municipalities: Belgrade (17 city municipalities) and Niš (5),
and the cities with one city municipality of their own beside them (Požarevac with Kostolac, Užice with Sevojno).

RIK has no row for such a city, so the site adds one page per city (g/<slug>.html) that adds its municipalities
up, by the same arithmetic as a municipality's page, and lists them. What a city is comes from the results
themselves (commission.city_parts: the names "<City>-<Part>", the district "Град <City>", or the one "Град …" in
the municipality's district), never from a list kept here. The only thing kept here is how Belgrade's
municipalities are usually grouped when people talk about the city, central and outer, so the table can show a
subtotal for each; the city's figures are always all of it, as RIK counts it."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from izbori.translit import latin

# Belgrade's ten central municipalities ("uži Beograd"); the other seven are the outer ones. Labels in i18n:
# city_group_central, city_group_outer. Any other city has no groups.
BELGRADE_CENTRAL = {"70106", "70114", "70149", "70157", "70181", "70203", "70211", "70220", "70246", "70254"}
GROUPED = {"BEOGRAD": ("central", "outer")}


@dataclass
class City:
    key: str  # commission.municipality_key of the city's name, e.g. "BEOGRAD"
    slug: str  # the page's name: g/<slug>.html
    name: str  # as RIK writes it, Cyrillic, without "Град"
    codes: list[str] = field(default_factory=list)  # every municipality that is part of it, the city's own first
    own: str | None = None  # the city's own municipality code, when the results have one (Požarevac, Užice)

    def group_of(self, code: str) -> str | None:
        if self.key not in GROUPED:
            return None
        central, outer = GROUPED[self.key]
        return central if code in BELGRADE_CENTRAL else outer

    def order(self, code: str, name: str) -> tuple:
        """The city's own municipality first, then the central group before the outer, then by name."""
        return (code != self.own, self.group_of(code) == GROUPED.get(self.key, ("", ""))[1], sort_key(name))


def slug_of(key: str) -> str:
    s = unicodedata.normalize("NFD", key.lower())
    return "".join(ch for ch in s if ch.isalnum() and not unicodedata.combining(ch))


def cities(city_parts: dict[str, tuple[str, str]], stations) -> dict[str, City]:
    """Every city with more than one municipality in the results, by slug. city_parts: commission.city_parts over
    every archived station; stations: the same stations, for the cities' names."""
    import re
    from izbori.boards import municipality_key
    names: dict[str, str] = {}  # city key → name as RIK writes it
    own_name: dict[str, str] = {}  # municipality code → its name
    for s in stations:
        own_name.setdefault(s.municipality_code, s.municipality)
        m = re.match(r"^(\S+)-\S", s.municipality)
        if m:
            names.setdefault(municipality_key(m.group(1)), m.group(1))
        last = (s.district or "").split("/")[-1]
        if re.match(r"^Град\s+", last):
            names.setdefault(municipality_key(last), re.sub(r"^Град\s+", "", last))
    out: dict[str, City] = {}
    for code, (kind, key) in sorted(city_parts.items()):
        if kind == "name":
            city = out.setdefault(slug_of(key), City(key, slug_of(key), names.get(key, key)))
        else:  # the city's own code: the city is named after it
            k = municipality_key(own_name.get(key, key))
            city = out.setdefault(slug_of(k), City(k, slug_of(k), re.sub(r"^Град\s+", "", own_name.get(key, key)),
                                                    own=key))
            if key not in city.codes:
                city.codes.insert(0, key)
        if code not in city.codes:
            city.codes.append(code)
    return {slug: c for slug, c in out.items() if len(c.codes) > 1}


def name_slug(name: str) -> str:
    """A municipality's address from its name: Latin, lowercase, ASCII, words joined by hyphens ("Нови Сад" →
    "novi-sad", "Градска општина Палилула (Београд)" → "palilula-beograd", "Град Пожаревац" → "grad-pozarevac" only
    when asked to keep the word, see slugs())."""
    import re
    s = latin(name).replace("Đ", "Dj").replace("đ", "dj").lower()
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


RESERVED = {"api", "cyr", "en", "lat", "feed", "g", "m", "r", "s", "static", "index"}


def slugs(names: dict[str, str], newest: set[str], city_slugs: set[str], own: set[str]) -> dict[str, str]:
    """Each municipality code → its address. names: code → name as RIK writes it; newest: the codes in the newest
    election (they win a shared name); city_slugs: the cities' addresses (a city's own municipality keeps the word
    "grad": grad-pozarevac beside the city's pozarevac); own: those municipalities' codes. A name two municipalities
    share, or one a city takes, gets the code appended."""
    out: dict[str, str] = {}
    taken = set(city_slugs) | RESERVED
    for code in sorted(names, key=lambda c: (c not in newest, c)):
        base = name_slug(names[code] if code in own else bare_name(names[code]))  # palilula-beograd, palilula-nis
        slug = base if base not in taken else f"{base}-{name_slug(code)}"
        taken.add(slug)
        out[code] = slug
    return out


def aliases(slug: str) -> list[str]:
    """Other spellings a reader may type: the words run together (novisad for novi-sad)."""
    return [slug.replace("-", "")] if "-" in slug else []


def add_up(rows: list[dict], stations: list) -> dict:
    """A city's figures from its municipalities' rows and stations, as municipalities() computes them."""
    counted = [s for s in stations if s.counted]
    reg = sum(s.registered for s in counted)
    voted = sum(s.voted for s in counted)
    ballots = sum(s.ballots or 0 for s in counted)
    invalid = sum(s.invalid or 0 for s in counted)
    flagged = sum(r["flagged"] for r in rows)
    n = sum(r["stations"] for r in rows)
    return {"stations": n, "counted": len(counted), "registered": reg, "voted": voted,
            "turnout": voted / reg if reg else None, "invalid": invalid / ballots if ballots else None,
            "flagged": flagged, "flagged_share": flagged / n if n else None, "municipalities": len(rows)}


def bare_name(name: str) -> str:
    """A municipality's name without the kind of municipality in front, the city in brackets kept."""
    import re
    return re.sub(r"^(Градска општина|Gradska opština|Град|Grad|Општина|Opština)\s+", "", name).strip()


def short_name(name: str) -> str:
    """A city municipality's name without the words every one of them has, and without the city in brackets
    ("Градска општина Палилула (Београд)" → "Палилула")."""
    import re
    name = re.sub(r"^(Градска општина|Gradska opština|Град|Grad|Општина|Opština)\s+", "", name)
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def sort_key(name: str) -> str:
    return latin(short_name(name))
