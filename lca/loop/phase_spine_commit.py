"""Phase fold spine fact commit seam (ADR-0194 P2-12).

Phase fold EPs commit via ``publish_ep_bound``. Production phase.tool.*
EPs live in ``tool_journal_commit``; loop-cursor fold EPs still route through
``spine_loop_cursor`` until that publisher migrates.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.loop.fact_gateway import publish_ep_bound


def commit_perceive_phase_fold(
    *,
    step: int,
    run_id: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "phase",
) -> AppendReceipt | None:
    return publish_ep_bound(
        "perceive.phase.fold",
        {"step": step, "run_id": run_id},
        state=state,
        session=session,
        actor=actor,
    )


def commit_phase_perceive_fold(
    *,
    step: int,
    run_id: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "phase",
) -> AppendReceipt | None:
    return publish_ep_bound(
        "phase.perceive.fold",
        {"step": step, "run_id": run_id},
        state=state,
        session=session,
        actor=actor,
    )


def commit_phase_think_fold(
    *,
    step: int,
    run_id: str,
    decision_path: str | None = None,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "phase",
) -> AppendReceipt | None:
    payload: dict[str, Any] = {"step": step, "run_id": run_id}
    if decision_path is not None:
        payload["decision_path"] = decision_path
    return publish_ep_bound(
        "phase.think.fold",
        payload,
        state=state,
        session=session,
        actor=actor,
    )


def commit_phase_remember_fold(
    *,
    step: int,
    run_id: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "phase",
) -> AppendReceipt | None:
    return publish_ep_bound(
        "phase.remember.fold",
        {"step": step, "run_id": run_id},
        state=state,
        session=session,
        actor=actor,
    )


def commit_phase_stop_fold(
    *,
    step: int,
    run_id: str,
    outcome: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "phase",
) -> AppendReceipt | None:
    return publish_ep_bound(
        "phase.stop.fold",
        {"step": step, "run_id": run_id, "outcome": outcome},
        state=state,
        session=session,
        actor=actor,
    )


def commit_phase_reflect_fold(
    *,
    step: int,
    run_id: str,
    lessons: int | None = None,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "phase",
) -> AppendReceipt | None:
    payload: dict[str, Any] = {"step": step, "run_id": run_id}
    if lessons is not None:
        payload["lessons"] = lessons
    return publish_ep_bound(
        "phase.reflect.fold",
        payload,
        state=state,
        session=session,
        actor=actor,
    )


def commit_phase_act_fold_start(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "phase",
) -> AppendReceipt | None:
    return publish_ep_bound(
        "phase.act.fold.start",
        {"step": step, "run_id": run_id, "tool_name": tool_name},
        state=state,
        session=session,
        actor=actor,
    )


def commit_phase_act_fold_end(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    outcome: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "phase",
) -> AppendReceipt | None:
    return publish_ep_bound(
        "phase.act.fold.end",
        {
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "outcome": outcome,
        },
        state=state,
        session=session,
        actor=actor,
    )


def commit_phase_act_fold(
    *,
    step: int,
    run_id: str,
    tool_name: str,
    outcome: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "phase",
) -> AppendReceipt | None:
    return publish_ep_bound(
        "phase.act.fold",
        {
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "outcome": outcome,
        },
        state=state,
        session=session,
        actor=actor,
    )


__all__ = [
    "commit_perceive_phase_fold",
    "commit_phase_act_fold",
    "commit_phase_act_fold_end",
    "commit_phase_act_fold_start",
    "commit_phase_perceive_fold",
    "commit_phase_reflect_fold",
    "commit_phase_remember_fold",
    "commit_phase_stop_fold",
    "commit_phase_think_fold",
]
