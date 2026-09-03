"""spine_reflector_writable plugin（ADR-0181 PR-5 / ADR-0183 PR-7）。

PR-5：writable matrix 全部 7 emit 下沉到 EventBus.publish：
- writable.step.start / .end
- writable.segment.start / .end
- writable.iteration.halt / .closing / .close

实际写入由 cursor._append + WritePort 接管；本 publisher 提供
EventBus 路径的 typed 入口。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    from lca_kernel.events.bus import EventBus

    cat_str = _SPINE_EP_TO_CATEGORY[execution_point]
    sp = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


# ── writable.step.start / .end ────────────────────────────────────────


def emit_writable_step_start(*, step: int, run_id: str) -> EventRef:
    return _send(
        execution_point="writable.step.start",
        channel="control",
        payload={"step": step, "run_id": run_id},
    )


def emit_writable_step_end(
    *,
    step: int,
    run_id: str,
    outcome: str = "success",
) -> EventRef:
    return _send(
        execution_point="writable.step.end",
        channel="control",
        payload={"step": step, "run_id": run_id, "outcome": outcome},
    )


# ── writable.segment.start / .end ────────────────────────────────────


def emit_writable_segment_start(*, segment: int, step: int, run_id: str) -> EventRef:
    return _send(
        execution_point="writable.segment.start",
        channel="control",
        payload={"segment": segment, "step": step, "run_id": run_id},
    )


def emit_writable_segment_end(
    *,
    segment: int,
    step: int,
    run_id: str,
    outcome: str = "success",
) -> EventRef:
    return _send(
        execution_point="writable.segment.end",
        channel="control",
        payload={
            "segment": segment,
            "step": step,
            "run_id": run_id,
            "outcome": outcome,
        },
    )


# ── writable.iteration.halt / .closing / .close ───────────────────────


def emit_writable_iteration_halt(*, run_id: str, reason: str) -> EventRef:
    return _send(
        execution_point="writable.iteration.halt",
        channel="control",
        payload={"run_id": run_id, "reason": reason},
    )


def emit_writable_iteration_closing(*, run_id: str) -> EventRef:
    return _send(
        execution_point="writable.iteration.closing",
        channel="control",
        payload={"run_id": run_id},
    )


def emit_writable_iteration_close(*, run_id: str) -> EventRef:
    return _send(
        execution_point="writable.iteration.close",
        channel="control",
        payload={"run_id": run_id},
    )


__all__ = [
    "ReflectorClass",
    "emit_writable_iteration_close",
    "emit_writable_iteration_closing",
    "emit_writable_iteration_halt",
    "emit_writable_segment_end",
    "emit_writable_segment_start",
    "emit_writable_step_end",
    "emit_writable_step_start",
]
