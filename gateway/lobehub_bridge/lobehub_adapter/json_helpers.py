"""JSON parsing and field extraction utilities.

Shared primitives used by argument adapters and state builders.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

# ── JSON parsing ────────────────────────────────────────────


def parse_args_json(raw: str) -> dict[str, Any]:
    """Parse a JSON arguments string; return ``{}`` on any failure."""
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def safe_json_string(raw: str) -> str:
    """Ensure *raw* is valid JSON; wrap in ``{"preview": ...}`` if not."""
    text = (raw or "").strip()
    if not text:
        return "{}"
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"preview": text[:200]})


# ── Field extraction ────────────────────────────────────────


def first_str(args: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty string value found under *keys*."""
    for key in keys:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def copy_fields(
    args: dict[str, Any],
    mapping: Sequence[tuple[str, str]] | dict[str, str],
) -> dict[str, Any]:
    """Generic field copy/rename.

    ``mapping`` is ``(source_key, dest_key)`` pairs.  Only non-empty
    string values and numeric values are copied.
    """
    items = mapping if isinstance(mapping, Sequence) else mapping.items()
    out: dict[str, Any] = {}
    for src, dst in items:
        val = args.get(src)
        if isinstance(val, str) and val.strip():
            out[dst] = val.strip()
        elif isinstance(val, (int, float)) and not isinstance(val, bool):
            out[dst] = val
    return out



