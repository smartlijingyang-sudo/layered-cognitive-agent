"""Test helpers for Session-bound gate/perceive facts."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from lca.contracts.harness.fold.perceive import fold_gate_decisions_from_events
from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perceive_projection import PerceiveProjection
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.infrastructure.session.bindings import resolve_session_reader
from lca.infrastructure.session.turn_control_reader import append_turn_control_fact
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


@contextmanager
def bound_session(session_id: str = "test_session") -> Iterator[Session]:
    session = Session(session_id)
    token = set_publish_session(session)
    try:
        yield session
    finally:
        reset_publish_session(token)


def append_control_turn(state: AgentState, turn: Turn) -> None:
    """Append one turn to ``state.history`` and Session ``turn.control.v1`` when bound."""
    state.history.append(turn)
    session = resolve_session_reader()
    if session is not None:
        append_turn_control_fact(session, turn)


def extend_control_turns(state: AgentState, turns: Iterable[Turn]) -> None:
    """Seed consecutive control turns for gate threshold tests."""
    for turn in turns:
        append_control_turn(state, turn)


def gate_decisions_for_step(state: AgentState, *, step: int | None = None) -> list[GateDecided]:
    """Fold gate.decided.v1 facts for one step from the bound Session."""
    session = resolve_session_reader()
    if session is None:
        return []
    target = state.step if step is None else step
    return fold_gate_decisions_from_events(session.snapshot_events(), step=target)


def seed_manifest_projection(
    state: AgentState,
    manifest: ContextManifest,
    *,
    step: int | None = None,
) -> None:
    """Write a synthetic manifest onto ``state.perceive`` for gate/harness tests."""
    target_step = state.step if step is None else step
    state.perceive = PerceiveProjection(
        manifest=manifest,
        digest=manifest.digest,
        step=target_step,
    )


__all__ = [
    "append_control_turn",
    "bound_session",
    "extend_control_turns",
    "gate_decisions_for_step",
    "seed_manifest_projection",
]
