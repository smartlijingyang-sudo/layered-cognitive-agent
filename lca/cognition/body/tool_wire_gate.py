"""工具调用 wire 执行闸门（ADR-0047）。

``Decision.extra.tool_wire_status`` 为 incomplete/invalid 时禁止执行工具，
返回 ``Observation(success=False)`` 回灌 cognitive loop。
纯函数模块，供 ``UseToolOperation`` 调用。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import MemoryRecordKind
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_TOOL_WIRE,
    OBS_RESULT_KIND,
    TOOL_WIRE_FINISH_REASON,
    TOOL_WIRE_INCOMPLETE,
    TOOL_WIRE_INVALID,
    TOOL_WIRE_RAW_PREVIEW,
    TOOL_WIRE_REASON,
    TOOL_WIRE_STATUS,
)
from lca.contracts.models.core.decision import Decision, Observation

_BLOCKING: frozenset[str] = frozenset({TOOL_WIRE_INCOMPLETE, TOOL_WIRE_INVALID})


def tool_wire_block_observation(decision: Decision) -> Observation | None:
    """若 wire 状态禁止执行，返回失败观测；否则 None（继续正常工具路径）。"""
    status = str(decision.extra.get(TOOL_WIRE_STATUS) or "")
    if status not in _BLOCKING:
        return None
    if not decision.tool_calls:
        return None
    tc = decision.tool_calls[0]
    reason = str(decision.extra.get(TOOL_WIRE_REASON) or status)
    finish = decision.extra.get(TOOL_WIRE_FINISH_REASON)
    preview = decision.extra.get(TOOL_WIRE_RAW_PREVIEW)
    parts = [
        f"tool_wire_{status}",
        f"tool={tc.tool_name}",
        f"reason={reason}",
    ]
    if finish:
        parts.append(f"finish_reason={finish}")
    parts.append(
        "arguments incomplete or invalid; do not treat as successful tool result; "
        "shorten code/args or split into smaller steps and retry"
    )
    extra: dict[str, object] = {
        FAILURE_KIND: FAILURE_KIND_TOOL_WIRE,
        OBS_RESULT_KIND: MemoryRecordKind.TOOL_RESULT,
        TOOL_WIRE_STATUS: status,
        TOOL_WIRE_REASON: reason,
    }
    if finish is not None:
        extra[TOOL_WIRE_FINISH_REASON] = finish
    if preview is not None:
        extra[TOOL_WIRE_RAW_PREVIEW] = preview
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error="; ".join(parts),
        tool_call_id=tc.call_id,
        extra=extra,
    )
