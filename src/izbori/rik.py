"""RIK's public results service: which rounds exist, counting progress, and the results CSV."""

from __future__ import annotations

import json
import re
from html import unescape
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from izbori.config import RIK_BASE, USER_AGENT

KIND_BY_TYPE = {2: "parliamentary", 3: "local", 7: "provincial"}
TYPES = range(1, 11)


class RikError(RuntimeError):
    pass


def guess_kind(rik_type: int, name: str) -> str:
    n = (name or "").lower()
    words = {  # stems: RIK names rounds briefly, e.g. "Парламентарни 2026", "Локални 2024 - Београд"
        "presidential": ("председни", "predsedni"),
        "provincial": ("покрајин", "pokrajin", "војводин", "vojvodin", "аутономн", "autonomn"),
        "local": ("одборни", "odborni", "локалн", "lokaln"),
        "parliamentary": ("посланик", "poslanik", "парламент", "parlament"),
    }
    for kind, stems in words.items():
        if any(w in n for w in stems):
            return kind
    return KIND_BY_TYPE.get(rik_type, "unknown")


def _flag(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "da"}


def _int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).replace(".", "").replace(",", "").strip())
    except ValueError:
        return None


@dataclass
class Summary:
    rik_type: int
    round: str
    counted: int | None
    total: int | None
    rik_time: str | None
    allowed: bool
    title: str = ""
    contestants: list[tuple[int, str]] = field(default_factory=list)
    voters: int | None = None

    @property
    def counting(self) -> bool:
        return self.counted is not None and self.total is not None and self.counted < self.total

    @property
    def signature(self) -> list:
        return [self.rik_time, self.counted, self.total]


def parse_summary(rik_type: int, rid: str, data: dict) -> Summary:
    stats = data.get("stat_sum_numbers") or {}
    contestants = []
    for i, row in enumerate(data.get("table_data") or []):
        name = str(row.get("list_name") or "").strip()
        m = re.match(r"^\s*(\d+)\s*[.)]\s*(.*)$", name)
        number = _int(row.get("count_number")) or (int(m.group(1)) if m else i + 1)
        contestants.append((number, m.group(2).strip() if m else name))
    contestants.sort()
    return Summary(
        rik_type=rik_type, round=str(rid),
        counted=_int(stats.get("processed_stations")), total=_int(stats.get("number_of_stations")),
        rik_time=(str(stats.get("datetime")).strip() or None) if stats.get("datetime") else None,
        allowed=_flag(stats.get("allowed_download")), title=str(stats.get("election_title") or "").strip(),
        contestants=contestants, voters=_int(stats.get("total_voters")),
    )


class Client:
    def __init__(self, base: str = RIK_BASE, timeout: float = 90, retries: int = 3, opener=None, sleep=time.sleep):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.open = opener or urllib.request.urlopen
        self.sleep = sleep

    def _request(self, path: str, form: dict | None = None) -> tuple[bytes, dict]:
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/csv, */*",
                   "X-Requested-With": "XMLHttpRequest"}
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        last = None
        for attempt in range(self.retries):
            req = urllib.request.Request(self.base + path, data=data, headers=headers)
            try:
                with self.open(req, timeout=self.timeout) as resp:
                    return resp.read(), dict(resp.headers.items())
            except urllib.error.HTTPError as e:
                last = e
                if e.code < 500 and e.code != 429:
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
            if attempt + 1 < self.retries:
                self.sleep(5 * 3 ** attempt)
        raise RikError(f"{path}: {last}")

    def _json(self, path: str, form: dict):
        body, _ = self._request(path, form)
        text = body.decode("utf-8-sig").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise RikError(f"{path}: not JSON ({text[:120]!r})") from e

    def elections(self, rik_type: int) -> dict[str, str]:
        data = self._json("/get-elections/", {"election_type": rik_type})
        if not isinstance(data, dict):
            return {}
        rounds = data.get("rounds") or {}
        if isinstance(rounds, list):
            return {str(r.get("id")): str(r.get("name", "")) for r in rounds if isinstance(r, dict)}
        return {str(k): str(v) for k, v in rounds.items()}

    def all_rounds(self) -> dict[str, dict]:
        found = {}
        for rik_type in TYPES:
            for rid, name in self.elections(rik_type).items():
                found[rid] = {"type": rik_type, "name": name, "kind": guess_kind(rik_type, name)}
        return found

    def summary(self, rik_type: int, rid: str) -> Summary:
        data = self._json("/get_results/", {
            "should_update_pies": 0, "type": rik_type, "election_round": rid,
            "region": 0, "municipality": 0, "election_station": 0,
        })
        return parse_summary(rik_type, rid, data or {})

    # --- RIK's results app, one level at a time (for rounds whose CSV can no longer be downloaded) ----
    def regions(self, rik_type: int, rid: str) -> dict[str, str]:
        data = self._json("/get-regions/", {"election_type": rik_type, "election_round": rid}) or {}
        return {str(k): str(v) for k, v in (data.get("regions") or {}).items()}

    def municipalities(self, rik_type: int, rid: str, region: str) -> list[tuple[str, str]]:
        body, _ = self._request("/get-municipalities/", {"election_type": rik_type, "election_round": rid,
                                                         "election_region": region})
        html = body.decode("utf-8-sig")
        return [(m.group(1), unescape(m.group(2)).strip())
                for m in re.finditer(r'value="?(\d+)"?[^>]*>([^<]+)<', html) if m.group(1) != "0"]

    def stations(self, rik_type: int, rid: str, region: str, municipality: str) -> dict[str, str]:
        data = self._json("/get-election-stations/", {"election_type": rik_type, "election_round": rid,
                                                      "election_region": region,
                                                      "election_municipality": municipality}) or {}
        return {str(k): str(v) for k, v in (data.get("election_stations") or {}).items()}

    def station_results(self, rik_type: int, rid: str, region: str, municipality: str, station: str) -> dict:
        return self._json("/get_results/", {"should_update_pies": 1, "type": rik_type, "election_round": rid,
                                            "region": region, "municipality": municipality,
                                            "election_station": station}) or {}

    def register_page(self, rid: str, rik_type: int, page: int, document_type: int | None = None) -> dict:
        """One page (ten polling stations) of RIK's register of minutes ("Записници") for a round: each station's
        documents with their labels, links and upload times. document_type limits it to stations having one kind
        (RIK's numbering: 12 is the observers' record, 29 a remark)."""
        form = {"page": page, "data[type]": 1, "data[election_round]": rid, "data[property_election_type]": rik_type,
                "election_type": rik_type}
        if document_type:
            form["filters[election_document_type]"] = document_type
        return self._json("/get-election", form) or {}

    def get_json(self, path: str):
        body, _ = self._request(path)
        return json.loads(body.decode("utf-8-sig") or "null")

    def get_bytes(self, path_or_url: str) -> bytes:
        """A document from RIK's site; Cyrillic in the path is percent-encoded first."""
        path = path_or_url.split("parlament.gov.rs", 1)[-1] if path_or_url.startswith("http") else path_or_url
        path = urllib.parse.quote(path, safe="/:?&=%@+,;~!$'()*")
        body, _ = self._request(path)
        return body

    def export(self, rid: str) -> tuple[bytes, str | None]:
        body, headers = self._request(f"/export-results/{rid}/2")
        if not body.lstrip(b"\xef\xbb\xbf").startswith(b"bm_uid"):
            raise RikError(f"export {rid}: not a results CSV ({body[:80]!r})")
        disposition = {k.lower(): v for k, v in headers.items()}.get("content-disposition", "")
        m = re.search(r'filename="?([^";]+)"?', disposition)
        return body, (m.group(1) if m else None)
