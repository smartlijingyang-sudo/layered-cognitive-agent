"""Canonical ToolStarted / ToolInvoked / ToolDenied emitters.

Per spec §9.1 + journal boundary guard, ``lca.layer1_cognitive.body.safe_executor``
is the single canonical emitter for the three tool lifecycle events.
Other consumers (e.g. ``pipeline_safe_executor``) must route through
this module so the journal sees exactly one emission site per event.
"""

from __future__ import annotations

import json
import time
from typing import Any

from lca.contracts.models.core.decision import Observation, ToolCall  # noqa: F401
from lca.contracts.models.observability.journal import (
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.contracts.protocols.infra import Tool
from lca.layer0_infra.observability import record
from lca.layer1_cognitive.body.tool_result_preview import (
    tool_files,
    tool_plugin_state,
)
from lca.layer1_cognitive.body.tool_ui_state import (
    build_started_plugin_state,
    compact_args_preview,
)


def _tool_output_preview(obs: Observation) -> str:
    """Compact success/error payload into a single-line preview."""
    if obs.success:
        return json.dumps(
            obs.payload,
            ensure_ascii=False,
            default=str,
        )
    return obs.error or ""


def emit_tool_started(
    tool: Tool,
    args_preview: str,
    invocation_id: str,
    started_state: dict[str, Any],
) -> None:
    """Emit ``ToolStarted`` from the canonical safe_executor module."""
    record(
        ToolStarted(
            tool_name=tool.name,
            arguments_preview=args_preview,
            invocation_id=invocation_id,
            plugin_state=started_state,
        )
    )


def emit_tool_denied(tool: Tool, reason: str) -> None:
    """Emit ``ToolDenied`` from the canonical safe_executor module."""
    record(ToolDenied(tool_name=tool.name, reason=reason))


def emit_tool_invoked(
    tool: Tool,
    args: dict[str, Any],
    args_preview: str,
    obs: Observation,
    *,
    latency_ms: int,
    attempt: int,
    invocation_id: str,
) -> None:
    """Emit ``ToolInvoked`` from the canonical safe_executor module."""
    resolved_id = str((obs.extra or {}).get("invocation_id", "") or "") or invocation_id
    record(
        ToolInvoked(
            tool_name=tool.name,
            arguments_preview=args_preview,
            result_preview=_tool_output_preview(obs),
            ok=obs.success,
            latency_ms=latency_ms,
            attempt=attempt,
            error="" if obs.success else (obs.error or ""),
            invocation_id=resolved_id,
            files=tool_files(obs),
            plugin_state=tool_plugin_state(obs, tool_name=tool.name, args=args),
        )
    )
