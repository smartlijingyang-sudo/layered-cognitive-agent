"""spine_reflector_team plugin（ADR-0181 PR-6 / ADR-0183 PR-7）。

PR-6：team 维度 7 EP 下沉到 EventBus.publish（新加，old manifest 没有）。

签名沿用 pilot delegation_cache 已落地的接口语义（typed payload + 业务方
一行 publish）。本 publisher 是 spine 侧 typed 入口，业务方在 EventBus
路径下统一调用。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.bus import EventBus
from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads import TeamDelegationCacheHit as TeamCacheHitPayload

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    category: Category,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    from lca_kernel.events.bus import EventBus

    sp = SpineEventPayload(
        category=category,
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


# ── team.casting.{started,completed,failed} ──────────────────────────


def emit_team_casting_started(
    *,
    team_id: str,
    requested_roles: list[str],
    run_id: str,
) -> EventRef:
    return _send(
        category=Category("spine.team.casting.started"),
        execution_point="team.casting.started",
        channel="control",
        payload={
            "team_id": team_id,
            "requested_roles": requested_roles,
            "run_id": run_id,
        },
    )


def emit_team_casting_completed(
    *,
    team_id: str,
    selected_roles: list[str],
    run_id: str,
) -> EventRef:
    return _send(
        category=Category("spine.team.casting.completed"),
        execution_point="team.casting.completed",
        channel="control",
        payload={
            "team_id": team_id,
            "selected_roles": selected_roles,
            "run_id": run_id,
        },
    )


def emit_team_casting_failed(
    *,
    team_id: str,
    reason: str,
    run_id: str,
) -> EventRef:
    return _send(
        category=Category("spine.team.casting.failed"),
        execution_point="team.casting.failed",
        channel="error",
        payload={"team_id": team_id, "reason": reason, "run_id": run_id},
    )


# ── team.delegation.{issued,completed,cache_hit} ─────────────────────


def emit_team_delegation_issued(
    *,
    team_id: str,
    callee_role: str,
    subtask: str,
    run_id: str,
) -> EventRef:
    return _send(
        category=Category("spine.team.delegation.issued"),
        execution_point="team.delegation.issued",
        channel="control",
        payload={
            "team_id": team_id,
            "callee_role": callee_role,
            "subtask": subtask,
            "run_id": run_id,
        },
    )


def emit_team_delegation_completed(
    *,
    team_id: str,
    callee_role: str,
    subtask: str,
    outcome: str,
    run_id: str,
) -> EventRef:
    return _send(
        category=Category("spine.team.delegation.completed"),
        execution_point="team.delegation.completed",
        channel="control",
        payload={
            "team_id": team_id,
            "callee_role": callee_role,
            "subtask": subtask,
            "outcome": outcome,
            "run_id": run_id,
        },
    )


def emit_team_delegation_cache_hit(
    *,
    team_id: str,
    callee_role: str,
    subtask: str,
    step: int,
    run_id: str,
) -> EventRef:
    """Emit ``spine.team.delegation.cache_hit`` typed via
    :class:`TeamDelegationCacheHit`（yaml SSOT 强制 payload class）。
    """
    return EventBus.default().publish(
        TeamCacheHitPayload(
            category=Category("spine.team.delegation.cache_hit"),
            callee_role=callee_role,
            subtask=subtask,
            step=step,
        ),
        producer=ReflectorClass,
    )


# ── team.message.published ───────────────────────────────────────────


def emit_team_message_published(
    *,
    team_id: str,
    sender: str,
    recipient: str,
    run_id: str,
) -> EventRef:
    return _send(
        category=Category("spine.team.message.published"),
        execution_point="team.message.published",
        channel="fact",
        payload={
            "team_id": team_id,
            "sender": sender,
            "recipient": recipient,
            "run_id": run_id,
        },
    )


__all__ = [
    "ReflectorClass",
    "emit_team_casting_completed",
    "emit_team_casting_failed",
    "emit_team_casting_started",
    "emit_team_delegation_cache_hit",
    "emit_team_delegation_completed",
    "emit_team_delegation_issued",
    "emit_team_message_published",
]

