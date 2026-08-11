"""Parse structured computer op results from guest stdout."""

from __future__ import annotations

import json
from typing import Any

from lca.layer0_infra.computer.constants import COMPUTER_RESULT_BEGIN, COMPUTER_RESULT_END


def parse_computer_stdout(stdout: str) -> dict[str, Any] | None:
    """Extract JSON payload embedded in guest stdout marker block."""
    start = stdout.find(COMPUTER_RESULT_BEGIN)
    end = stdout.find(COMPUTER_RESULT_END)
    if start < 0 or end < 0 or end <= start:
        return None
    raw = stdout[start + len(COMPUTER_RESULT_BEGIN) : end]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
