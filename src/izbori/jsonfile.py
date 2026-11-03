"""The derived stores as JSON with one entry per line, so that git keeps a small diff when a few entries change.

Each store is a dict with one big mapping (decisions, documents, stations) and a few small values. The small values
go on the first line and each entry of the mapping on a line of its own, keys sorted, so the file is valid JSON and
`json.loads` reads it back unchanged."""

from __future__ import annotations

import json


def dumps(data: dict, entries: str) -> str:
    """data as JSON text, data[entries] one entry per line."""
    head = ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False, sort_keys=True)}"
                     for k, v in sorted(data.items()) if k != entries)
    lines = ",\n".join(f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False, sort_keys=True)}"
                       for k, v in sorted((data.get(entries) or {}).items()))
    return "{" + (head + ", " if head else "") + json.dumps(entries) + ": {" + ("\n" + lines + "\n" if lines else "") \
        + "}}\n"
