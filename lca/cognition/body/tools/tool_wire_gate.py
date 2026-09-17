"""工具调用 wire 执行闸门（ADR-0047）。

``Decision.extra.tool_wire_status`` 为 incomplete/invalid 时禁止执行工具，
返回 ``Observation(success=False)`` 回灌 cognitive loop。
纯函数模块，供 ``UseToolOperation`` 调用。
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryRecordKind
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import (
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
from lca.contracts.models.core.execution.decision import Decision, Observation

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


def required_arguments(tool: object) -> tuple[str, ...]:
    """Read a tool's JSON-schema ``required`` argument names, tolerantly."""
    parameters = getattr(tool, "parameters", None)
    if not isinstance(parameters, dict):
        return ()
    required = parameters.get("required")
    if not isinstance(required, (list, tuple)):
        return ()
    return tuple(str(name) for name in required if isinstance(name, str) and name)


def missing_arguments_block_observation(
    decision: Decision,
    tool_registry: object,
) -> Observation | None:
    """若某个 tool_call 的必填参数整体缺席，返回失败观测；否则 None。

    ``arguments`` 空着到达 Body 只有一个来源:wire 上的 arguments 被截断或
    结构非法(ADR-0047 分类为 incomplete/invalid)。此时照常执行等于用空载荷
    调工具,回给模型的是一个不指向真因的下游错误 —— ``run_445b582f0a90``
    的 ``writeFile`` 没有 path,抛 ``IsADirectoryError: /mnt/data``,run 就此
    收口。闸门在这里挡住,并把「缩短参数 / 拆小步骤」的指令回灌给模型。
    """
    if not decision.tool_calls:
        return None
    get = getattr(tool_registry, "get", None)
    if not callable(get):
        return None
    for tc in decision.tool_calls:
        tool = get(tc.tool_name)
        required = required_arguments(tool)
        if not required:
            continue
        provided = tc.arguments or {}
        if any(name in provided for name in required):
            continue
        parts = [
            "tool_wire_incomplete",
            f"tool={tc.tool_name}",
            "reason=missing_required_arguments",
            f"required={','.join(required)}",
            "arguments incomplete or invalid; do not treat as successful tool result; "
            "shorten code/args or split into smaller steps and retry",
        ]
        extra: dict[str, object] = {
            FAILURE_KIND: FAILURE_KIND_TOOL_WIRE,
            OBS_RESULT_KIND: MemoryRecordKind.TOOL_RESULT,
            TOOL_WIRE_STATUS: TOOL_WIRE_INCOMPLETE,
            TOOL_WIRE_REASON: "missing_required_arguments",
        }
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error="; ".join(parts),
            tool_call_id=tc.call_id,
            extra=extra,
        )
    return None
