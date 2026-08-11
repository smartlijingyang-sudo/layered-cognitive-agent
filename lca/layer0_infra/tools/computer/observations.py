"""Build computer use observations for journal + LobeHub wire."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_EXECUTION
from lca.contracts.models.core.decision import Observation
from lca.layer0_infra.computer.runtime import ComputerOpResult


def build_computer_observation(
    result: ComputerOpResult,
    *,
    tool_name: str,
    start: float,
) -> Observation:
    del tool_name
    latency_ms = int((time.monotonic() - start) * 1000)
    payload: dict[str, Any] = {
        **result.state,
        "content": result.content,
        "summary": _truncate(result.content),
    }
    if result.exec_result is not None:
        payload["exit_code"] = result.exec_result.exit_code

    if not result.success:
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=payload,
            content_type=ContentType.STRUCTURED,
            error=result.error or result.content or "computer operation failed",
            latency_ms=latency_ms,
            extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
        )

    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=payload,
        content_type=ContentType.STRUCTURED,
        latency_ms=latency_ms,
    )


def _truncate(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
