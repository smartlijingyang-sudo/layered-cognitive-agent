"""spine_reflector_control plugin（ADR-0181 PR-6 / ADR-0183 PR-7）。

PR-6：control 维度 11 EP（新加，old manifest 没有）。

控制面事件：dispatch / invoke / approve / deny / revoke / pause / resume /
stop / signal / accept。这些是控制指令的事实记录，区别于 reflection /
exception / lifecycle 等观察类事件。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    category: str,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    from lca_kernel.events.bus import EventBus

    sp = SpineEventPayload(
        category=Category(category),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


# ── dispatch / invoke / signal ────────────────────────────────────────


def emit_control_dispatch(*, run_id: str, target: str, intent: str) -> EventRef:
    return _send(
        category="spine.control.dispatch",
        execution_point="control.dispatch",
        channel="control",
        payload={"run_id": run_id, "target": target, "intent": intent},
    )


def emit_control_invoke(*, run_id: str, target: str, args: dict[str, Any]) -> EventRef:
    return _send(
        category="spine.control.invoke",
        execution_point="control.invoke",
        channel="control",
        payload={"run_id": run_id, "target": target, "args": args},
    )


def emit_control_signal(*, run_id: str, name: str, payload: dict[str, Any]) -> EventRef:
    return _send(
        category="spine.control.signal",
        execution_point="control.signal",
        channel="fact",
        payload={"run_id": run_id, "name": name, "payload": payload},
    )


# ── approve / deny / revoke ──────────────────────────────────────────


def emit_control_approve_request(*, run_id: str, request_id: str, intent: str) -> EventRef:
    return _send(
        category="spine.control.approve.request",
        execution_point="control.approve.request",
        channel="control",
        payload={"run_id": run_id, "request_id": request_id, "intent": intent},
    )


def emit_control_approve_response(
    *,
    run_id: str,
    request_id: str,
    verdict: str,
    actor: str,
) -> EventRef:
    return _send(
        category="spine.control.approve.response",
        execution_point="control.approve.response",
        channel="control",
        payload={
            "run_id": run_id,
            "request_id": request_id,
            "verdict": verdict,
            "actor": actor,
        },
    )


def emit_control_deny(*, run_id: str, request_id: str, reason: str) -> EventRef:
    return _send(
        category="spine.control.deny",
        execution_point="control.deny",
        channel="control",
        payload={"run_id": run_id, "request_id": request_id, "reason": reason},
    )


def emit_control_revoke(*, run_id: str, target: str) -> EventRef:
    return _send(
        category="spine.control.revoke",
        execution_point="control.revoke",
        channel="control",
        payload={"run_id": run_id, "target": target},
    )


# ── pause / resume / stop / accept ───────────────────────────────────


def emit_control_pause(*, run_id: str, reason: str) -> EventRef:
    return _send(
        category="spine.control.pause",
        execution_point="control.pause",
        channel="control",
        payload={"run_id": run_id, "reason": reason},
    )


def emit_control_resume(*, run_id: str) -> EventRef:
    return _send(
        category="spine.control.resume",
        execution_point="control.resume",
        channel="control",
        payload={"run_id": run_id},
    )


def emit_control_stop(*, run_id: str, outcome: str = "success") -> EventRef:
    return _send(
        category="spine.control.stop",
        execution_point="control.stop",
        channel="control",
        payload={"run_id": run_id, "outcome": outcome},
    )


def emit_control_accept(*, run_id: str, request_id: str) -> EventRef:
    return _send(
        category="spine.control.accept",
        execution_point="control.accept",
        channel="control",
        payload={"run_id": run_id, "request_id": request_id},
    )


__all__ = [
    "ReflectorClass",
    "emit_control_accept",
    "emit_control_approve_request",
    "emit_control_approve_response",
    "emit_control_deny",
    "emit_control_dispatch",
    "emit_control_invoke",
    "emit_control_pause",
    "emit_control_resume",
    "emit_control_revoke",
    "emit_control_signal",
    "emit_control_stop",
]
