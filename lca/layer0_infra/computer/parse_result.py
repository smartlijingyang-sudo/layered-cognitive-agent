"""Parse structured computer op results from guest stdout."""

from __future__ import annotations

import json
from typing import Any

from lca.layer0_infra.computer.constants import COMPUTER_RESULT_BEGIN, COMPUTER_RESULT_END


def parse_computer_stdout(stdout: str) -> dict[str, Any] | None:
    """Extract JSON payload from guest stdout.

    Prefers the LCA marker block (needed when execute() appends the artifact
    scanner). Falls back to native LobeHub style: last JSON object line.
    """
    start = stdout.find(COMPUTER_RESULT_BEGIN)
    end = stdout.find(COMPUTER_RESULT_END)
    if start >= 0 and end > start:
        raw = stdout[start + len(COMPUTER_RESULT_BEGIN) : end]
        payload = _as_object(raw)
        if payload is not None:
            return payload
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            payload = _as_object(stripped)
            if payload is not None:
                return payload
    return None


def _as_object(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
