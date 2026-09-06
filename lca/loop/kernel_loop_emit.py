"""Kernel boot + loop fork spine EP production (ADR-0194 P2-14)."""

from __future__ import annotations

from lca.contracts.models.core.state import AgentState
from lca.loop.spine_ep_emit import SpineEmitRef, publish_spine_ep

_KERNEL_ACTOR = "kernel"


def emit_kernel_boot_start(
    *,
    profile: str,
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    return publish_spine_ep(
        "kernel.boot.start",
        {"profile": profile},
        channel="control",
        actor=_KERNEL_ACTOR,
        state=state,
        session=session,
    )


def emit_kernel_boot_completed(
    *,
    profile: str,
    outcome: str = "success",
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    return publish_spine_ep(
        "kernel.boot.completed",
        {"profile": profile, "outcome": outcome},
        channel="control",
        actor=_KERNEL_ACTOR,
        state=state,
        session=session,
    )


def emit_loop_fork(
    *,
    child_role: str,
    parent_step: int,
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    return publish_spine_ep(
        "loop.fork",
        {"child_role": child_role, "parent_step": parent_step},
        channel="control",
        actor=_KERNEL_ACTOR,
        state=state,
        session=session,
    )


__all__ = [
    "emit_kernel_boot_completed",
    "emit_kernel_boot_start",
    "emit_loop_fork",
]
