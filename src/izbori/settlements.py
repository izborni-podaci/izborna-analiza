"""Each polling station's settlement in the 2022 census.

A polling station serves part of a settlement (naselje), and the census counts people by settlement (census.py,
data/census/2022/). Each round's stations are joined to the census, the same way for every station, the first rule
that answers deciding:

1. a manual correction in data/settlements.csv, where a maintainer recorded one: "manual";
2. a settlement of the station's municipality named in the address read from its board decision, after its first
   part ("ОШ Бранко Радичевић, Нови Бановци, …"): "address";
3. named in the address's first part ("Дом културе Голубинци", "Голубинци, Путиначка 1"): "building";
4. named in the station's name in the results: "station";
5. the municipality has a single settlement, as Belgrade's urban city municipalities do: "single";
6. the same polling place in another election (places.py) found its settlement by one of the rules above:
   "place";
7. an address with a street or a house number that names no settlement: the settlement bearing the municipality's
   name ("Стара Пазова", "Младеновац (варош)", "Београд (Вождовац)"): "seat". This one is assumed: a town's
   stations are usually given by building and street, without the town's name.

Otherwise the station has no settlement: unknown is not zero. Names are compared in Latin without diacritics,
word by word, and the longest name wins, so "Нови Бановци" is never read as a shorter name inside it. A name the
census qualifies in brackets is also found without them when that leaves no doubt: "Београд" is Voždovac's
"Београд (Вождовац)", "Младеновац" the town, "Младеновац (варош)", rather than the village, "Младеновац (село)".
An address that names another building than the station's name in the results is not used, as everywhere else
(places.contradicts).

The census prints names, never codes: its municipalities and settlements are a hierarchy shown by the first
column's indentation (areas and municipalities at 2, a city's city municipalities at 3, settlements at 4; 1 marks
the urban and other subtotals). RIK's municipalities are matched to them by name, without "Град" or "Градска
општина", a name in brackets saying which city ("Палилула (Ниш)"); a city's city municipality that RIK doesn't list
in a round belongs to the city's own (Vranjska Banja to Vranje in 2026). Kosovo and Metohija had no census.

data/rounds/<id>/settlements.json keeps, per station, the census municipality ("u", with its city before a colon
for a city municipality: "Град Ниш: Палилула"), the settlement as the census prints it ("s"), and the rule that
found it ("m"). data/settlements.csv has the columns round, municipality_code, number, settlement, note.

The pages compare places by a few of the census's figures for each settlement (load_figures): RZS's type, urban
or other; the population in 2011 and 2022; and the people aged 65 or more. They are read from the archived tables
when the site is built, keyed as settlements.json names a settlement."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

from izbori import jsonfile
from izbori.model import Station
from izbori.places import Places, contradicts
from izbori.translit import latin

TABLES = Path("census") / "2022" / "settlements"  # under the data dir
TABLE = TABLES / "0_ukupan-broj-stanovnika-naselja.xlsx"
POPULATION = TABLES / "4_uporedni-pregled-broja-stanovnika-1948-2022.xlsx"  # every census from 1948
AGES = TABLES / "1_stanovnistvo-prema-starosti-i-polu.xlsx"
FIGURE_TABLES = (POPULATION, AGES)
STORE = "settlements.json"
RULES_FILE = "settlements.csv"
HOW = ("manual", "list", "address", "building", "station", "single", "place", "seat", "rest")  # the rules, in order
DIRECT = {"manual", "list", "address", "building", "station", "single"}  # what another election may pass on
PREFIXES = ("GRADSKA OPSTINA ", "GRAD ", "OPSTINA ")
PLACE_WORDS = {"GRAD", "OBLAST", "UPRAVNI", "OKRUG", "OPSTINA", "GRADSKA"}  # say nothing about which place
STREET = re.compile(r"\b(UL|ULICA|BR|BROJ|BB|TRG|BUL|BULEVAR|PUT|SOKAK|NASELJE)\b")
STREET_OR_NUMBER = re.compile(r"\d|\b(UL|ULICA|BR|BROJ|BB|TRG|BUL|BULEVAR|SOKAK)\b")
BRACKETS = re.compile(r"^(.*?)\s*\((.*)\)\s*$")


def norm(text) -> str:
    """Upper-case Latin without diacritics, words only: the form in which names are compared."""
    s = latin(str(text or "")).upper().replace("Đ", "DJ")
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[A-Z0-9]+", s))


@dataclass
class Unit:
    """A municipality or a city's city municipality in the census, with its settlements."""
    name: str  # as printed: "Палилула"
    city: str = ""  # the city whose city municipality it is: "Град Ниш"
    area: str = ""  # "Нишавска област"
    settlements: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.city}: {self.name}" if self.city else self.name


def _walk(path: Path):
    """(census municipality, settlement, the settlement's row) for every settlement of a table by settlement. The
    hierarchy is the first column's indentation: areas and municipalities at 2 (a city printed with settlements of
    its own is a municipality too), a city's city municipalities at 3, settlements at 4; 1 marks the urban and
    other subtotals. A table with several rows per place (by sex) names the place in the first only."""
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True).active
    area = city = ""
    cur: Unit | None = None
    for row in ws.iter_rows(min_row=2):
        cell = row[0]
        if cell.value is None or not isinstance(cell.value, str):
            continue
        level = int(cell.alignment.indent or 0) if cell.alignment else 0
        name = re.sub(r"\s+", " ", cell.value).strip()
        if level == 2:
            city = ""
            if "област" in name.lower():
                area, cur = name, None
                continue
            if name.startswith("Град "):
                city = name  # its city municipalities follow
            cur = Unit(name, "", area)
        elif level == 3:
            cur = Unit(name, city, area)
        elif level == 4 and cur is not None:
            yield cur, name, row


def load_units(path: Path) -> list[Unit]:
    """The census's municipalities with their settlements, from a table by settlement (the total population)."""
    units: list[Unit] = []
    for u, name, _ in _walk(path):
        if not u.settlements:
            units.append(u)
        u.settlements.append(name)
    return units


@dataclass(frozen=True)
class Figures:
    """A settlement in the 2022 census: RZS's type and the figures the pages compare places by."""
    urban: bool  # "г" in the census: RZS's urban settlement; the rest are "other"
    pop2011: int | None  # None where the 2011 census gives none (Preševo and Bujanovac, by settlement)
    pop2022: int | None
    old: int | None = None  # people aged 65 or more in 2022

    @property
    def change(self) -> float | None:
        """The population's change from 2011 to 2022, as a fraction: -0.12 is 12% fewer people."""
        if not self.pop2011 or self.pop2022 is None:
            return None
        return self.pop2022 / self.pop2011 - 1

    @property
    def share_old(self) -> float | None:
        """The share of the people aged 65 or more."""
        return self.old / self.pop2022 if self.old is not None and self.pop2022 else None


def _count(value) -> int | None:
    """A count as RZS prints it: "-" is none, "..." (or anything else that isn't a number) unknown."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return 0 if str(value or "").strip() == "-" else None


_FIGURES: dict[tuple, dict] = {}  # read once per process for the same files: tests build the site many times


def load_figures(data_dir: Path) -> dict[tuple[str, str], Figures]:
    """Per (census municipality, settlement), named as in settlements.json: the settlement's type, its population in
    2011 and 2022, and its people aged 65 or more. Empty when the census isn't archived."""
    data_dir = Path(data_dir)
    if not (data_dir / POPULATION).exists():
        return {}
    files = [data_dir / f for f in FIGURE_TABLES]
    key = tuple((str(f.resolve()), f.stat().st_mtime_ns, f.stat().st_size) if f.exists() else (str(f), 0, 0)
                for f in files)
    if key not in _FIGURES:
        _FIGURES.clear()
        _FIGURES[key] = _read_figures(data_dir)
    return _FIGURES[key]


def _read_figures(data_dir: Path) -> dict[tuple[str, str], Figures]:
    out: dict[tuple[str, str], Figures] = {}
    for u, name, row in _walk(data_dir / POPULATION):  # B: "г" for urban; C to K: 1948, 1953, … 2011, 2022
        out[(u.key, name)] = Figures(urban=str(row[1].value or "").strip() == "г", pop2011=_count(row[9].value),
                                     pop2022=_count(row[10].value))
    if (data_dir / AGES).exists():
        for u, name, row in _walk(data_dir / AGES):  # D: everyone; E to V: 0-4, 5-9, … 80-84, 85 and more
            f = out.get((u.key, name))
            ages = [_count(c.value) for c in row[17:22]]  # 65-69 to 85 and more
            if f is not None:
                out[(u.key, name)] = replace(f, old=None if None in ages else sum(ages))
    return out


def rik_name(name: str) -> tuple[list[str], list[str]]:
    """RIK's municipality name as words, without "Град" or "Градска општина", and the words of a name in brackets:
    "Градска општина Палилула (Ниш)" → (["PALILULA"], ["NIS"])."""
    m = BRACKETS.match(name or "")
    base, qual = (m.group(1), m.group(2)) if m else (name or "", "")
    b = norm(base)
    for p in PREFIXES:
        if b.startswith(p):
            b = b[len(p):]
            break
    return b.split(), norm(qual).split()


class Census:
    """The census's municipalities, found by RIK's names."""

    def __init__(self, units: list[Unit]):
        self.units = units
        self.by_name: dict[str, list[Unit]] = defaultdict(list)
        for u in units:
            self.by_name[norm(u.name)].append(u)

    @staticmethod
    def _place_words(u: Unit) -> set[str]:
        return set(norm(f"{u.city} {u.area}").split()) - PLACE_WORDS

    def unit(self, name: str, district: str = "") -> Unit | None:
        """The census municipality RIK's name stands for; None when there is none (Kosovo and Metohija, abroad,
        prisons) or it can't be told apart."""
        base, qual = rik_name(name)
        tries = [(base, qual)]
        # "Ниш-Медијана" (2022): the city first, then its city municipality
        tries += [(base[k:], qual + base[:k]) for k in range(1, len(base))]
        for words, q in tries:
            cands = self.by_name.get(" ".join(words), [])
            if q and len(cands) > 1:
                cands = [u for u in cands if set(q) & self._place_words(u)] or cands
            if len(cands) > 1 and district:
                d = set(norm(district).split()) - PLACE_WORDS
                cands = [u for u in cands if d & self._place_words(u)] or cands
            if len(cands) == 1:
                return cands[0]
            if cands:
                return None
        return None

    def for_round(self, stations: list[Station]) -> dict[str, list[Unit]]:
        """Per RIK municipality code, its census municipalities: its own, then any city municipality of the same
        city that RIK doesn't list in this round."""
        out: dict[str, list[Unit]] = {}
        for s in stations:
            if s.municipality_code not in out:
                u = self.unit(s.municipality, s.district)
                out[s.municipality_code] = [u] if u else []
        claimed = {id(us[0]) for us in out.values() if us}
        for us in out.values():
            if us and us[0].city:
                us += [u for u in self.units if u.city == us[0].city and id(u) not in claimed]
        return out


@dataclass
class Rules:
    """Manual corrections: (round, station key) → settlement; and (round, municipality code) → the settlement every
    station of the municipality that no rule places belongs to (number "*" in the file: the maintainer checked
    that the commission writes bare building names for the town's stations only)."""
    settlement: dict[tuple[str, str], str] = field(default_factory=dict)
    rest: dict[tuple[str, str], str] = field(default_factory=dict)


def load_rules(path: Path | None, log=None) -> Rules:
    rules = Rules()
    if path is None or not Path(path).exists():
        return rules
    with open(path, encoding="utf-8", newline="") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            row = {k: (v or "").strip() for k, v in row.items() if k}
            if not all(row.get(k) for k in ("round", "municipality_code", "number", "settlement")):
                if log:
                    log(f"{path}:{n}: needs a round, a municipality, a station number and a settlement")
                continue
            if row["number"] == "*":
                rules.rest[(row["round"], row["municipality_code"])] = row["settlement"]
            else:
                rules.settlement[(row["round"], f"{row['municipality_code']}/{row['number']}")] = row["settlement"]
    return rules


def names(units: list[Unit]) -> list[tuple[str, str, Unit]]:
    """(name as compared, as printed, municipality) for every settlement, longest first; a name qualified in
    brackets also without them, when only one settlement would answer to it (a town before a village of its name)."""
    out = [(norm(s), s, u) for u in units for s in u.settlements]
    have = {n for n, _, _ in out}
    bare: dict[str, list[tuple[str, Unit, str]]] = defaultdict(list)
    for u in units:
        for s in u.settlements:
            m = BRACKETS.match(s)
            if m:
                bare[norm(m.group(1))].append((s, u, norm(m.group(2))))
    for b, items in bare.items():
        if not b or b in have:
            continue
        if len(items) > 1:
            items = [i for i in items if i[2] == "VAROS"] or items
        if len(items) == 1:
            out.append((b, items[0][0], items[0][1]))
    return sorted(out, key=lambda t: -len(t[0]))


def _find(known: list[tuple[str, str, Unit]], texts: list[str]) -> tuple[Unit, str] | None:
    for n, printed, u in known:
        if any(f" {n} " in f" {t} " for t in texts if t):
            return u, printed
    return None


def seat(units: list[Unit]) -> str | None:
    """The settlement bearing the municipality's name: "Стара Пазова", "Младеновац (варош)", "Београд (Вождовац)"."""
    own = norm(units[0].name)
    found = [s for s in units[0].settlements
             if norm(s) in (own, own + " VAROS") or (BRACKETS.match(s) and norm(s).endswith(" " + own))]
    return found[0] if len(found) == 1 else None


def match(station: Station, units: list[Unit], address: str = "") -> tuple[Unit, str, str] | None:
    """The station's census municipality, settlement and the rule that found it (rules 2 to 5, and 7; rule 6 needs
    the other elections, see inherit)."""
    if not units:
        return None
    known = names(units)
    if address and contradicts(station.name, address):
        address = ""
    parts = [norm(p) for p in address.split(",")] if address else []
    after = parts[1:]
    hit = _find(known, [p for p in after if not STREET.search(p)]) or _find(known, after)
    if hit:
        return hit[0], hit[1], "address"
    if parts and (hit := _find(known, parts[:1])):
        return hit[0], hit[1], "building"
    if hit := _find(known, [norm(station.name)]):
        return hit[0], hit[1], "station"
    if len({(u.key, s) for _, s, u in known}) == 1:
        return known[0][2], known[0][1], "single"
    if parts and STREET_OR_NUMBER.search(" ".join(parts)) and (s := seat(units)):
        return units[0], s, "seat"
    return None


def join(stations: list[Station], census: Census, addresses: dict[str, str], rid: str = "",
         rules: Rules | None = None, log=None, listed: dict[str, str] | None = None) -> dict[str, dict]:
    """Per station key: {"u": census municipality, "s": settlement, "m": the rule}; stations with none are left
    out. Rule 6 (the same place in another election) is added by inherit, once every round is joined."""
    rules = rules or Rules()
    units = census.for_round(stations)
    out: dict[str, dict] = {}
    for s in stations:
        us = units.get(s.municipality_code, [])
        manual = rules.settlement.get((rid, s.key))
        if manual:
            found = [u for u in us if manual in u.settlements]
            if found:
                out[s.key] = {"u": found[0].key, "s": manual, "m": "manual"}
                continue
            if log:
                log(f"{RULES_FILE}: {rid} {s.key}: {manual} is not a settlement of {s.municipality}")
        in_act = (listed or {}).get(s.key)  # the commission's decision on polling stations names the settlement
        if in_act:
            found = [u for u in us if in_act in u.settlements]
            if found:
                out[s.key] = {"u": found[0].key, "s": in_act, "m": "list"}
                continue
        hit = match(s, us, addresses.get(s.key, ""))
        if hit:
            out[s.key] = {"u": hit[0].key, "s": hit[1], "m": hit[2]}
            continue
        rest = rules.rest.get((rid, s.municipality_code))
        if rest:  # the maintainer's rule for the municipality's stations no other rule places
            found = [u for u in us if rest in u.settlements]
            if found:
                out[s.key] = {"u": found[0].key, "s": rest, "m": "rest"}
            elif log:
                log(f"{RULES_FILE}: {rid} {s.municipality_code}/*: {rest} is not a settlement of {s.municipality}")
    return out


def inherit(joined: dict[str, dict[str, dict]], places: Places) -> int:
    """Rule 6: a station with no settlement, or only the assumed seat, takes the one its polling place found by a
    rule from 1 to 5 in another election, the newest such election first. joined is per round, changed in place;
    returns how many stations took one."""
    n = 0
    for p in places.places:
        found = [joined.get(rid, {}).get(p.stations[rid].key) for rid in p.rounds]  # newest election first
        direct = [e for e in found if e and e["m"] in DIRECT]
        if not direct:
            continue
        best = direct[0]
        for rid in p.rounds:
            key = p.stations[rid].key
            e = joined.get(rid, {}).get(key)
            if e is None or e["m"] == "seat":
                joined.setdefault(rid, {})[key] = {"u": best["u"], "s": best["s"], "m": "place"}
                n += 1
    return n


def store_path(round_dir: Path) -> Path:
    return Path(round_dir) / STORE


def load_store(round_dir: Path) -> dict:
    p = store_path(round_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_store(round_dir: Path, joined: dict[str, dict]) -> bool:
    """Write the round's store; False when it was already the same."""
    text = jsonfile.dumps({"census": "2022", "stations": joined}, "stations")
    p = store_path(round_dir)
    if p.exists() and p.read_text(encoding="utf-8") == text:
        return False
    p.write_text(text, encoding="utf-8")
    return True


def summary(stations: list[Station], joined: dict[str, dict], units: dict[str, list[Unit]] | None = None) -> Counter:
    """How the round's stations were joined, and why the rest weren't."""
    def why(s: Station) -> str:
        if s.key in joined:
            return joined[s.key]["m"]
        if s.kind != "domestic":
            return "abroad or prison"
        if units is not None and not units.get(s.municipality_code):
            return "no census"
        return "none"
    return Counter(why(s) for s in stations)
