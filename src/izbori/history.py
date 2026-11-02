"""The archive: every distinct results file RIK published, with a log of what changed at each station.

Layout, one folder per round:

    data/rounds.json                  rounds RIK lists, by id
    data/rounds/<id>/meta.json        type, title, contestants, contest rules
    data/rounds/<id>/results.csv      latest file exactly as downloaded; git history keeps every version
    data/rounds/<id>/snapshots.jsonl  one line per distinct file: fetch time, RIK time, progress, SHA-256
    data/rounds/<id>/changes.jsonl    one line per changed value at a station after it first had results
    data/rounds/<id>/first_seen.json  when each station first had results in the archive
    data/rounds/<id>/flags_seen.json  when each flag first appeared
    data/rounds/<id>/state.json       RIK's progress at the last change, to skip unchanged downloads
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from izbori.load import HEAD, NUMBERS, TAIL, parse, read_rows
from izbori.model import Contestant, Round

IGNORED = {"bm_uid", "vreme_unosa_rezultata"}  # RIK rewrites entry times in bulk; uid is internal


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def is_number_field(name: str) -> bool:
    """Registered, voted, ballots, valid, invalid, or one contestant's votes."""
    return name in NUMBERS or (name not in HEAD and name not in TAIL and not name.startswith("*"))


@dataclass
class SnapshotResult:
    sha256: str
    changes: list[dict] = field(default_factory=list)
    new_stations: list[str] = field(default_factory=list)


class Archive:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.rounds_dir = self.root / "rounds"

    # --- files -------------------------------------------------------------------------------
    def dir(self, rid: str) -> Path:
        return self.rounds_dir / str(rid)

    def _read_json(self, path: Path, default):
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")

    def _read_lines(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _append_lines(self, path: Path, rows: list[dict]) -> None:
        if not rows:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    # --- rounds ------------------------------------------------------------------------------
    def known_rounds(self) -> dict:
        return self._read_json(self.root / "rounds.json", {})

    def save_known_rounds(self, rounds: dict) -> None:
        self._write_json(self.root / "rounds.json", rounds)

    def round_ids(self) -> list[str]:
        if not self.rounds_dir.exists():
            return []
        ids = [p.name for p in self.rounds_dir.iterdir() if (p / "results.csv").exists()]
        return sorted(ids, key=lambda rid: self.first_fetch(rid) or "")

    def meta(self, rid: str) -> dict:
        return self._read_json(self.dir(rid) / "meta.json", {})

    def save_meta(self, rid: str, meta: dict) -> None:
        self._write_json(self.dir(rid) / "meta.json", meta)

    def state(self, rid: str) -> dict:
        return self._read_json(self.dir(rid) / "state.json", {})

    def save_state(self, rid: str, state: dict) -> None:
        self._write_json(self.dir(rid) / "state.json", state)

    def snapshots(self, rid: str) -> list[dict]:
        return self._read_lines(self.dir(rid) / "snapshots.jsonl")

    def first_fetch(self, rid: str) -> str | None:
        snaps = self.snapshots(rid)
        return snaps[0]["fetched"] if snaps else None

    def changes(self, rid: str) -> list[dict]:
        return self._read_lines(self.dir(rid) / "changes.jsonl")

    def first_seen(self, rid: str) -> dict:
        return self._read_json(self.dir(rid) / "first_seen.json", {})

    def flags_seen(self, rid: str) -> dict:
        return self._read_json(self.dir(rid) / "flags_seen.json", {})

    def save_flags_seen(self, rid: str, seen: dict) -> None:
        self._write_json(self.dir(rid) / "flags_seen.json", seen)

    def latest_raw(self, rid: str) -> bytes | None:
        p = self.dir(rid) / "results.csv"
        return p.read_bytes() if p.exists() else None

    # --- loading -----------------------------------------------------------------------------
    def load(self, rid: str) -> Round:
        meta = self.meta(rid)
        raw = self.latest_raw(rid)
        if raw is None:
            raise FileNotFoundError(f"no results archived for round {rid}")
        known = meta.get("contestants") or []
        stations, n = parse(raw, len(known) or None)
        contestants = []
        for i in range(n):
            c = known[i] if i < len(known) else {}
            contestants.append(Contestant(number=i + 1, name=c.get("name") or f"{i + 1}",
                                          short=c.get("short", ""), minority=bool(c.get("minority"))))
        snaps = self.snapshots(rid)
        last = snaps[-1] if snaps else {}
        return Round(id=str(rid), kind=meta.get("kind", "unknown"), title=meta.get("title", str(rid)),
                     contestants=contestants, stations=stations, contest=meta.get("contest", {}),
                     rik_time=last.get("rik_time"), fetched=last.get("fetched"))

    # --- writing a snapshot ------------------------------------------------------------------
    def add_snapshot(self, rid: str, raw: bytes, fetched: str | None = None, rik_time: str | None = None,
                     total: int | None = None, filename: str | None = None) -> SnapshotResult | None:
        """Archive `raw` if it differs from the latest file. Returns None when nothing changed."""
        fetched = fetched or now_iso()
        digest = sha256(raw)
        prev = self.latest_raw(rid)
        if prev is not None and sha256(prev) == digest:
            return None
        _, new_rows = read_rows(raw)
        old_rows = read_rows(prev)[1] if prev is not None else []
        result = SnapshotResult(sha256=digest)
        seen = self.first_seen(rid)
        old_by_key = {_key(r): r for r in old_rows}
        events = []
        for r in new_rows:
            key = _key(r)
            has_results = bool((r.get("glasali_biraci") or "").strip())
            old = old_by_key.pop(key, None)
            if has_results and key not in seen:
                seen[key] = fetched
                result.new_stations.append(key)
                continue
            if old is None or key not in seen:
                continue
            for col, value in r.items():
                if col in IGNORED:
                    continue
                before = (old.get(col) or "").strip()
                after = (value or "").strip()
                if before != after:
                    events.append({"t": fetched, "s": key, "f": col, "o": before, "n": after})
        for key in old_by_key:
            if key in seen:
                events.append({"t": fetched, "s": key, "f": "*station*", "o": "present", "n": "removed"})
        counted = sum(1 for r in new_rows if (r.get("glasali_biraci") or "").strip())
        d = self.dir(rid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "results.csv").write_bytes(raw)
        self._append_lines(d / "snapshots.jsonl", [{
            "fetched": fetched, "rik_time": rik_time, "counted": counted,
            "total": total if total is not None else len(new_rows), "stations": len(new_rows),
            "sha256": digest, "bytes": len(raw), "file": filename,
        }])
        self._append_lines(d / "changes.jsonl", events)
        self._write_json(d / "first_seen.json", seen)
        result.changes = events
        return result


def _key(row: dict) -> str:
    return f"{(row.get('sifra_opstine') or '').strip()}/{(row.get('bm_broj') or '').strip()}"
