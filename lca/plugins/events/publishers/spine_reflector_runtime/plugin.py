"""spine_reflector_runtime plugin（ADR-0181 PR-3 / ADR-0183 PR-7）。

PR-3：runtime 全部 8 emit 下沉到 EventBus.publish：
- exception.caught / exception.finally / lifecycle.finally
- runtime.reducer.apply（start + end）/ checkpoint.create /
  resume.start / resume.end / event_publisher.publish

signature 严格对齐旧 lca/plugins/observability/spine/reflectors/runtime.py
调用方零改动。

业务方一行调：
    EventBus.default().publish(
        SpineEventPayload(execution_point="...", channel="...", payload={...}),
        producer=ReflectorClass,
    )
"""

from __future__ import annotations

import logging
from typing import Any

from lca_kernel.events.bus import EventBus
from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> Any:
    """内部 helper：构造 SpineEventPayload + EventBus.publish。

    category 由 execution_point 通过 _SPINE_EP_TO_CATEGORY 派生。
    outcome（旧 reflector EventRecord.outcome）写进 payload，保留旧 API。
    """
    cat_str = _SPINE_EP_TO_CATEGORY[execution_point]
    sp = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


# ADR-2026-09-02-i17-traceback §D5: runtime reflector 需要 thread
# active run_id。tests 用 set_active_run_id 注入。
_active_run_id: str = ""


def set_active_run_id(run_id: str | None) -> None:
    """Install the active run_id for runtime EP payloads."""
    global _active_run_id
    _active_run_id = str(run_id or "")


def _coerce_run_id(explicit: str | None) -> str:
    """Resolve ``run_id`` with explicit-first, active-fallback semantics."""
    return str(explicit or "") or _active_run_id


# ── runtime.reducer.apply ────────────────────────────────────────────
#
# Reducer Protocol 是 AgentState C4 single-writer (ADR-0070)。
# 每次 apply_* fold 是 fact mutation 边界，spine 一次 emit + payload method 名。


def emit_runtime_reducer_apply_start(
    *,
    method: str,
    run_id: str | None = None,
) -> Any:
    """Emit ``runtime.reducer.apply`` start-side marker for one apply_* call."""
    return _send(
        execution_point="runtime.reducer.apply",
        channel="fact",
        payload={
            "method": method,
            "phase": "start",
            "run_id": _coerce_run_id(run_id),
        },
    )


def emit_runtime_reducer_apply_end(
    *,
    method: str,
    outcome: str,
    run_id: str | None = None,
) -> Any:
    """Emit ``runtime.reducer.apply`` end-side marker for one apply_* call."""
    return _send(
        execution_point="runtime.reducer.apply",
        channel="fact",
        payload={
            "method": method,
            "phase": "end",
            "outcome": outcome,
            "run_id": _coerce_run_id(run_id),
        },
    )


# ── runtime.checkpoint.create ─────────────────────────────────────────


def emit_runtime_checkpoint_create(
    *,
    plan_ref: str,
    state_ref: str,
    node_id: str,
    outcome: str = "success",
) -> Any:
    """Emit when a DeclarativeCheckpoint is materialised for resume."""
    return _send(
        execution_point="runtime.checkpoint.create",
        channel="control",
        payload={
            "plan_ref": plan_ref,
            "state_ref": state_ref,
            "node_id": node_id,
            "outcome": outcome,
        },
    )


# ── runtime.resume.start / runtime.resume.end ──────────────────────────


def emit_runtime_resume_start(
    *,
    plan_ref: str,
    state_ref: str,
    node_id: str,
) -> Any:
    """Emit at the entry of CognitiveRuntime.resume before driver handoff."""
    return _send(
        execution_point="runtime.resume.start",
        channel="control",
        payload={
            "plan_ref": plan_ref,
            "state_ref": state_ref,
            "node_id": node_id,
        },
    )


def emit_runtime_resume_end(
    *,
    plan_ref: str,
    state_ref: str,
    node_id: str,
    outcome: str,
) -> Any:
    """Emit at the end of CognitiveRuntime.resume after driver handoff.

    ``outcome`` is ``"success"`` on a normal terminal return; ``"failure"``
    if the driver raised; ``"cancelled"`` if asyncio.CancelledError.
    """
    return _send(
        execution_point="runtime.resume.end",
        channel="control",
        payload={
            "plan_ref": plan_ref,
            "state_ref": state_ref,
            "node_id": node_id,
            "outcome": outcome,
        },
    )


# ── runtime.event_publisher.publish ──────────────────────────────────
#
# 包每个 RuntimeLifecyclePublisher.publish 调用；spine 与既有 subscriber
# chain 并行承担 fact stream。


def emit_runtime_event_publisher_publish(
    *,
    event_type: str,
    trace_id: str,
    outcome: str = "success",
) -> Any:
    """Emit at every call to ``RuntimeLifecyclePublisher.publish``."""
    return _send(
        execution_point="runtime.event_publisher.publish",
        channel="control",
        payload={
            "event_type": event_type,
            "trace_id": trace_id,
            "outcome": outcome,
        },
    )


# ── runtime.observed（PR-6 新加 category）──────────────────────────────
#
# 解释流 marker：记录"某处发生了不改变领域状态的观察事件"。reader 凭
# ``runtime.observed`` 聚合事实流 + 解释流，避免理解任何 runtime.* EP
# 时遗漏"看到但没改"的边角。


def emit_runtime_observed(
    *,
    observed_at: str,
    detail: str,
    run_id: str | None = None,
) -> Any:
    """Emit ``runtime.observed`` marker (PR-6 new category).

    ``observed_at`` 是 runtime 内的 subsystem name（"checkpoint_persist" /
    "loop_cursor_advance" 等），``detail`` 自由文本。runtime.* 详细 EP
    仍走 spine_reflector_runtime 既有 emit_*，本 helper 仅在 runtime
    想表达"我已经记下了某个状态观察，无需进一步结构化"时使用。
    """
    return _send(
        execution_point="runtime.observed",
        channel="diagnostic",
        payload={
            "observed_at": observed_at,
            "detail": detail,
            "run_id": run_id or "",
        },
    )


# ── exception.caught / exception.finally ──────────────────────────────
#
# ``exception.caught`` 是 runner 抛出后转发时 emit；``exception.finally``
# 是 paired envelope，upstream handler 已记录 boundary event 后，downstream
# 消费者依赖严格 start/end 配对做清理。


def emit_exception_caught(
    *,
    boundary: str,
    exc_type: str,
    message: str,
    trace_id: str | None = None,
) -> Any:
    """Emit when the runtime layer catches an exception at a known boundary."""
    return _send(
        execution_point="exception.caught",
        channel="error",
        payload={
            "boundary": boundary,
            "exc_type": exc_type,
            "message": message,
            "trace_id": trace_id or "",
            "outcome": "failure",
        },
    )


def emit_exception_finally(
    *,
    boundary: str,
    trace_id: str | None = None,
    outcome: str = "failure",
) -> Any:
    """Emit ``exception.finally`` —— 仅异常路径（ADR-0166 S5）。

    正常路径请用 :func:`emit_lifecycle_finally`；本 helper 仅在异常边界
    收口时使用。默认 ``outcome="failure"``；cancelled 也走本 EP。
    """
    return _send(
        execution_point="exception.finally",
        channel="diagnostic",
        payload={
            "boundary": boundary,
            "trace_id": trace_id or "",
            "outcome": outcome,
        },
    )


def emit_lifecycle_finally(
    *,
    boundary: str,
    trace_id: str | None = None,
) -> Any:
    """Emit ``lifecycle.finally`` —— 正常路径收口（ADR-0166 S5）。"""
    return _send(
        execution_point="lifecycle.finally",
        channel="control",
        payload={
            "boundary": boundary,
            "trace_id": trace_id or "",
            "outcome": "success",
        },
    )


__all__ = [
    "ReflectorClass",
    "emit_exception_caught",
    "emit_exception_finally",
    "emit_lifecycle_finally",
    "emit_runtime_checkpoint_create",
    "emit_runtime_event_publisher_publish",
    "emit_runtime_observed",
    "emit_runtime_reducer_apply_end",
    "emit_runtime_reducer_apply_start",
    "emit_runtime_resume_end",
    "emit_runtime_resume_start",
    "set_active_run_id",
]
