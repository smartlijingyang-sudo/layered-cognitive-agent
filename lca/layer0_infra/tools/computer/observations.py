"""Build computer use observations for journal + LobeHub wire."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_EXECUTION
from lca.contracts.models.core.decision import Observation
from lca.layer0_infra.computer.runtime import ComputerOpResult
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.text.truncate import ASCII_ELLIPSIS, truncate_text
from lca.layer0_infra.tools.sandbox_observation import _stored_part
from lca.layer0_infra.workspace.scope import get_run_workspace

_COMPUTER_TRUNCATE_LIMIT = 8000


def build_computer_observation(
    result: ComputerOpResult,
    *,
    tool_name: str,
    start: float,
    store: FileStore,
) -> Observation:
    """Build an Observation from a ComputerOpResult, storing generated files."""
    latency_ms = int((time.monotonic() - start) * 1000)
    payload: dict[str, Any] = {
        **result.state,
        "content": result.content,
        "summary": _truncate(result.content),
    }
    if result.exec_result is not None:
        payload["exit_code"] = result.exec_result.exit_code

    # File pipeline: store generated files and record in workspace ledger
    file_parts: list[dict[str, Any]] = []
    for gen in result.generated_files:
        file_parts.append(_stored_part(store, gen.data, gen.name, gen.mime_type))

    extra: dict[str, Any] = {}
    if file_parts:
        extra["files"] = file_parts

    if not result.success:
        extra[FAILURE_KIND] = FAILURE_KIND_EXECUTION
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=payload,
            content_type=ContentType.STRUCTURED,
            error=result.error or result.content or "computer operation failed",
            latency_ms=latency_ms,
            extra=extra,
        )

    # Record in workspace artifact ledger (aligned with build_exec_observation)
    if file_parts:
        workspace = get_run_workspace()
        if workspace is not None:
            workspace.artifacts.record_from_tool_files(
                file_parts, tool_name=tool_name, agent_role=""
            )

    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=payload,
        content_type=ContentType.STRUCTURED,
        latency_ms=latency_ms,
        extra=extra,
    )


def _truncate(text: str, limit: int = _COMPUTER_TRUNCATE_LIMIT) -> str:
    return truncate_text(text, limit - len(ASCII_ELLIPSIS), suffix=ASCII_ELLIPSIS)
