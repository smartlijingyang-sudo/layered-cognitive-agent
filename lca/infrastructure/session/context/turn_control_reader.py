"""Read control-plane turn summaries from Session projection (ADR-0191 Wave C).

Wave C1 closure: gates consume :class:`TurnControlProjection` exclusively.
The legacy ``state.control_turns`` history fallback is removed — gates
no longer read history directly (ADR-0191 §C1). When no Session is
bound the reader returns an empty tuple; gates must treat empty as
"no control signal" rather than re-reading in-process state.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, cast

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.harness.memory.events import TurnControlCommitted
from lca.contracts.models.core.execution.decision import Turn
from lca.contracts.models.core.state.state import AgentState
from lca.harness.session.emit import emit
from lca.infrastructure.session._overflow_0.bindings import resolve_session_reader
from lca.plugins.session.session_turn_control.session_turn_control import TurnControlUnit
from lca_kernel.events.session.session import SessionEvent, SessionProtocol

_TURN_CONTROL = "turn.control.v1"


def _action_type_text(value: object) -> str:
    if isinstance(value, ActionType):
        return value.value
    if isinstance(value, str) and value.startswith("ActionType."):
        member_name = value.removeprefix("ActionType.")
        member = getattr(ActionType, member_name, None)
        if isinstance(member, ActionType):
            return member.value
    return str(value)


def _files_created_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item))
    return ()


@dataclass(frozen=True, slots=True)
class ControlTurnView:
    """Gate-facing turn summary folded from durable Session facts."""

    action_type: str
    tool_name: str | None = None
    observation_success: bool | None = None
    tool_arguments: dict[str, object] | None = None
    observation_payload: object | None = None
    observation_error: str | None = None
    files_created: tuple[str, ...] = ()


def append_turn_control_fact(session: SessionProtocol, turn: Turn) -> None:
    """Append one ``turn.control.v1`` fact for TurnControlUnit fold.

    ``observation_files_created`` is imported lazily to avoid a circular
    import between this module (used by cognition convergence) and
    ``lca.cognition.convergence.payload``.
    """
    from lca.cognition.convergence.payload import observation_files_created

    decision = turn.decision
    tool_name = decision.tool_calls[0].tool_name if decision.tool_calls else None
    observation = turn.observation
    tool_arguments = decision.tool_calls[0].arguments if decision.tool_calls else None
    emit(
        session,
        TurnControlCommitted(
            action_type=_action_type_text(decision.action_type),
            tool_name=tool_name,
            observation_success=observation.success if observation is not None else None,
            tool_arguments=tool_arguments,
            observation_payload=observation.payload if observation is not None else None,
            observation_error=observation.error if observation is not None else None,
            files_created=observation_files_created(observation),
        ),
    )


def fold_control_turns_from_events(events: Sequence[SessionEvent]) -> tuple[ControlTurnView, ...]:
    """Fold ``turn.control.v1`` events into gate-facing turn summaries.

    ``turn.ended.v1`` markers are session-end hints used to advance the
    last-action cursor inside the fold; they are not gate-facing control
    entries and are dropped from the view.
    """
    unit = TurnControlUnit()
    state = unit.init(None)
    for event in events:
        state = unit.apply(state, event)
    raw_turns = unit.view(state).get("turns") or []
    return tuple(
        ControlTurnView(
            action_type=_action_type_text(item.get("action_type") or ""),
            tool_name=item.get("tool_name") if item.get("tool_name") is not None else None,
            observation_success=item.get("observation_success"),
            tool_arguments=item.get("tool_arguments")
            if isinstance(item.get("tool_arguments"), dict)
            else None,
            observation_payload=item.get("observation_payload"),
            observation_error=(
                str(item.get("observation_error"))
                if item.get("observation_error") is not None
                else None
            ),
            files_created=_files_created_tuple(item.get("files_created")),
        )
        for item in raw_turns
        if isinstance(item, dict) and "turn" not in item
    )


def projected_control_turns(state: AgentState) -> tuple[ControlTurnView, ...] | None:
    """Return Session-folded turns when a bound Session exists."""
    session = resolve_session_reader()
    if session is None:
        return None
    snapshot = getattr(session, "snapshot_events", None)
    if not callable(snapshot):
        return None
    folded = fold_control_turns_from_events(tuple(cast("Any", snapshot)()))
    return folded


def control_turns(state: AgentState) -> tuple[ControlTurnView, ...]:
    """Session projection only (ADR-0191 §C1 — gates do not read history).

    Returns an empty tuple when no Session is bound. Callers that still
    need to project from in-process state should explicitly opt in via
    ``projected_control_turns``; reading ``state.control_turns`` is
    forbidden on this code path.
    """
    del state
    projected = projected_control_turns(None)
    return projected or ()


def iter_control_turns_reversed(state: AgentState) -> Iterator[ControlTurnView]:
    """Newest-first control turns for gate loop detectors."""
    yield from reversed(control_turns(state))


def last_observation_success(state: AgentState) -> bool | None:
    """Last committed turn observation success, if any."""
    turns = control_turns(state)
    if not turns:
        return None
    return turns[-1].observation_success


def consecutive_same_tool(state: AgentState, tool_name: str) -> int:
    """Count consecutive USE_TOOL turns targeting ``tool_name`` (newest first)."""
    count = 0
    for turn in iter_control_turns_reversed(state):
        if (
            turn.action_type != ActionType.USE_TOOL.value
            and turn.action_type != ActionType.USE_TOOL
        ):
            break
        if turn.tool_name != tool_name:
            break
        count += 1
    return count


def consecutive_identical_tool_calls(state: AgentState, fingerprint: str | None) -> int:
    """Count consecutive USE_TOOL turns with the same tool+args fingerprint."""
    if not fingerprint:
        return 0
    from lca.cognition.brain.decision_gates.loop.fingerprint import view_tool_fingerprint

    count = 0
    for turn in iter_control_turns_reversed(state):
        if (
            turn.action_type != ActionType.USE_TOOL.value
            and turn.action_type != ActionType.USE_TOOL
        ):
            break
        if view_tool_fingerprint(turn) != fingerprint:
            break
        count += 1
    return count


__all__ = [
    "ControlTurnView",
    "append_turn_control_fact",
    "consecutive_identical_tool_calls",
    "consecutive_same_tool",
    "control_turns",
    "fold_control_turns_from_events",
    "iter_control_turns_reversed",
    "last_observation_success",
    "projected_control_turns",
]
