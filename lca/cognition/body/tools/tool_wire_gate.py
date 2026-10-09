"""工具调用 wire 执行闸门（ADR-0047）。

``Decision.extra.tool_wire_status`` 为 incomplete/invalid 时禁止执行工具，
返回 ``Observation(success=False)`` 回灌 cognitive loop。
纯函数模块，供 ``UseToolOperation`` 调用。
"""

from __future__ import annotations

from collections.abc import Sequence

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

_WIRE_BLOCK_GUIDANCE = (
    "arguments incomplete or invalid; do not treat as successful tool result; "
    "shorten code/args or split into smaller steps and retry"
)


def _wire_block_observation(
    *,
    status: str,
    reason: str,
    tool_name: str,
    call_id: str,
    middle_parts: Sequence[str] = (),
    guidance: str = _WIRE_BLOCK_GUIDANCE,
    finish_reason: object = None,
    raw_preview: object = None,
) -> Observation:
    """Single constructor seam for wire-gate blocking Observations.

    The gates supply only condition + status + reason (+ gate-specific
    middle parts); the guidance text is single-sourced here so the
    product text cannot drift between gates.  Public gate signatures
    are unchanged.
    """
    parts = [
        f"tool_wire_{status}",
        f"tool={tool_name}",
        f"reason={reason}",
        *middle_parts,
        guidance,
    ]
    extra: dict[str, object] = {
        FAILURE_KIND: FAILURE_KIND_TOOL_WIRE,
        OBS_RESULT_KIND: MemoryRecordKind.TOOL_RESULT,
        TOOL_WIRE_STATUS: status,
        TOOL_WIRE_REASON: reason,
    }
    if finish_reason is not None:
        extra[TOOL_WIRE_FINISH_REASON] = finish_reason
    if raw_preview is not None:
        extra[TOOL_WIRE_RAW_PREVIEW] = raw_preview
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error="; ".join(parts),
        tool_call_id=call_id,
        extra=extra,
    )


def tool_wire_block_observation(decision: Decision) -> Observation | None:
    """若 wire 状态禁止执行，返回失败观测；否则 None（继续正常工具路径）。

    判定读 ``ToolCall`` 自带的 ADR-0047 字段(判定随调用透传的唯一真值),
    ``Decision.extra`` 只作回退:think 侧的 ``decision.parse`` 不写 extra,
    只认 extra 会把真实截断原因降级成 status 字面量回灌给模型。
    """
    if not decision.tool_calls:
        return None
    tc = decision.tool_calls[0]
    status = (tc.wire_status or "").strip() or str(decision.extra.get(TOOL_WIRE_STATUS) or "")
    if status not in _BLOCKING:
        return None
    reason = (tc.wire_reason or "").strip() or str(decision.extra.get(TOOL_WIRE_REASON) or status)
    finish = decision.extra.get(TOOL_WIRE_FINISH_REASON)
    preview = (tc.wire_raw_preview or "").strip() or decision.extra.get(TOOL_WIRE_RAW_PREVIEW)
    return _wire_block_observation(
        status=status,
        reason=reason,
        tool_name=tc.tool_name,
        call_id=tc.call_id,
        middle_parts=[f"finish_reason={finish}"] if finish else [],
        finish_reason=finish,
        raw_preview=preview,
    )


def unexposed_tool_block_observation(decision: Decision) -> Observation | None:
    """Refuse a call whose schema was not on this turn's tool list.

    Defer hides a namespace until ``tool_search`` loads it. The registry
    still holds the tool. Executing a name the model was not given is the
    fail-closed side of that hide. No defer session means the legacy full list.
    """

    from lca.infrastructure.tool_defer.session import current_defer_session

    session = current_defer_session()
    if session is None or not session.policy.enabled or not session.namespaces:
        return None
    wire, _catalog = session.render_turn()
    visible: set[str] = set()
    for spec in wire:
        function = spec.get("function") if isinstance(spec, dict) else None
        name = function.get("name") if isinstance(function, dict) else ""
        if isinstance(name, str) and name:
            visible.add(name)

    tool_to_ns: dict[str, str] = {}
    for ns_obj in session.namespaces:
        for tname in ns_obj.tool_names:
            tool_to_ns[tname] = ns_obj.name

    for tc in decision.tool_calls:
        if tc.tool_name in visible:
            continue
        ns_name = tool_to_ns.get(tc.tool_name, "deferred")
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=(
                f"tool {tc.tool_name} belongs to deferred namespace '{ns_name}' "
                "which is not loaded this turn. "
                "Call tool_search for its namespace before using it."
            ),
            tool_call_id=tc.call_id,
            extra={
                FAILURE_KIND: FAILURE_KIND_TOOL_WIRE,
                OBS_RESULT_KIND: MemoryRecordKind.TOOL_RESULT,
                TOOL_WIRE_STATUS: TOOL_WIRE_INVALID,
                TOOL_WIRE_REASON: "namespace_not_loaded",
            },
        )
    return None


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
        return _wire_block_observation(
            status=TOOL_WIRE_INCOMPLETE,
            reason="missing_required_arguments",
            tool_name=tc.tool_name,
            call_id=tc.call_id,
            middle_parts=[f"required={','.join(required)}"],
        )
    return None
