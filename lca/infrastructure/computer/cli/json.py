"""Interpret structured CLI stdout (officecli --json and kin)."""

from __future__ import annotations

import json


def cli_json_success(stdout: str) -> bool | None:
    """Return the JSON ``success`` flag when stdout is one object, else None.

    officecli uses exit 2 for warnings while still emitting ``{"success": true}``.
    The JSON flag is the command outcome; the process exit code is not.
    """
    text = (stdout or "").strip()
    if not text.startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "success" not in payload:
        return None
    return bool(payload["success"])
