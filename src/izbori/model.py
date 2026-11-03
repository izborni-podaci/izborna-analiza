"""Polling stations, contestants and rounds as read from RIK's results file."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

ABROAD = "/33000"
PRISONS = "/55001"

_STAMP = re.compile(r"/([0-9a-f]{13})/@")
_FORM = re.compile(r"РГ-7-\d+")


@dataclass
class Station:
    key: str  # municipality code + "/" + station number; stable across elections
    uid: str  # RIK's internal id, only valid within one round
    number: str
    name: str
    municipality: str
    municipality_code: str
    district: str
    district_code: str
    registered: int | None
    voted: int | None  # voters who signed the voter list
    ballots: int | None  # ballots found in the box
    valid: int | None
    invalid: int | None
    entered: str
    votes: list[int | None]
    minutes: str = ""  # raw "label|url" from RIK
    correction: str = ""

    @property
    def counted(self) -> bool:
        return self.voted is not None and self.registered is not None

    @property
    def kind(self) -> str:
        if self.district_code == ABROAD:
            return "abroad"
        if self.district_code == PRISONS:
            return "prison"
        return "domestic"

    @property
    def turnout(self) -> float | None:
        if not self.counted or not self.registered:
            return None
        return self.voted / self.registered

    @property
    def invalid_share(self) -> float | None:
        base = self.ballots or self.voted
        if self.invalid is None or not base:
            return None
        return self.invalid / base

    @property
    def minutes_links(self) -> list[tuple[str, str]]:
        """Every minutes document, oldest first (a repeat vote adds its own)."""
        return links(self.minutes)

    @property
    def correction_links(self) -> list[tuple[str, str]]:
        return links(self.correction)

    @property
    def minutes_url(self) -> str:
        """The latest minutes (form RG-2), not an observers' record or a remark listed with them."""
        from izbori.documents import classify
        found = [url for label, url in links(self.minutes) if classify(label)[0] == "minutes"]
        return found[-1] if found else last_url(self.minutes)

    @property
    def correction_url(self) -> str:
        return last_url(self.correction)

    @property
    def minutes_uploaded(self) -> datetime | None:
        m = _STAMP.search(self.minutes or "")
        if not m:
            return None
        return datetime.fromtimestamp(int(m.group(1)[:8], 16), tz=UTC)

    @property
    def correction_form(self) -> str:
        m = _FORM.findall(self.correction or "")
        return m[-1].replace("РГ", "RG") if m else ""

    @property
    def region(self) -> str:
        return self.district.split("/")[0] if "/" in self.district else self.district

    @property
    def district_name(self) -> str:
        return self.district.split("/")[-1]


def links(raw: str) -> list[tuple[str, str]]:
    """RIK's link fields hold one or more "label|url" entries, one per line."""
    out = []
    for part in (raw or "").split("\n"):
        part = part.strip()
        if not part:
            continue
        label, _, url = part.rpartition("|") if "|" in part else ("", "", part)
        if url.strip().startswith("http"):
            out.append((label.strip(), url.strip()))
    return out


def last_url(raw: str) -> str:
    found = links(raw)
    return found[-1][1] if found else ""


@dataclass
class Contestant:
    number: int
    name: str
    short: str = ""
    minority: bool = False

    @property
    def label(self) -> str:
        return self.short or self.name


@dataclass
class Round:
    id: str
    kind: str  # presidential, parliamentary, local, provincial or unknown
    title: str
    contestants: list[Contestant]
    stations: list[Station]
    contest: dict = field(default_factory=dict)
    rik_time: str | None = None
    fetched: str | None = None

    @property
    def counted(self) -> list[Station]:
        return [s for s in self.stations if s.counted]

    def station(self, key: str) -> Station | None:
        for s in self.stations:
            if s.key == key:
                return s
        return None
