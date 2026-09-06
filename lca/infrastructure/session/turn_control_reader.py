"""Read control-plane turn summaries from Session projection (ADR-0191 Wave C)."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from lca.contracts.atoms.enums import ActionType
from lca.contracts.harness.memory.events import TurnControlCommitted
from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.state import AgentState
from lca.harness.session.emit import emit
from lca.infrastructure.session.bindings import resolve_session_reader
from lca.plugins.session.session_turn_control.session_turn_control import TurnControlUnit
from lca_kernel.events.session import SessionEvent

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


@dataclass(frozen=True, slots=True)
class ControlTurnView:
    """Gate-facing turn summary folded from durable Session facts."""

    action_type: str
    tool_name: str | None = None
    observation_success: bool | None = None
    tool_arguments: dict[str, object] | None = None
    observation_payload: object | None = None
    observation_error: str | None = None


def append_turn_control_fact(session: object, turn: Turn) -> None:
    """Append one ``turn.control.v1`` fact for TurnControlUnit fold."""
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
        ),
    )


def fold_control_turns_from_events(events: Sequence[SessionEvent]) -> tuple[ControlTurnView, ...]:
    """Fold ``turn.control.v1`` events into gate-facing turn summaries."""
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
        )
        for item in raw_turns
        if isinstance(item, dict)
    )


def projected_control_turns(state: AgentState) -> tuple[ControlTurnView, ...] | None:
    """Return Session-folded turns when a bound Session exists."""
    session = resolve_session_reader()
    if session is None:
        return None
    snapshot = getattr(session, "snapshot_events", None)
    if not callable(snapshot):
        return None
    folded = fold_control_turns_from_events(tuple(snapshot()))
    return folded


def _history_control_turns(state: AgentState) -> tuple[ControlTurnView, ...]:
    views: list[ControlTurnView] = []
    for turn in state.control_turns:
        if not isinstance(turn, Turn):
            continue
        decision = turn.decision
        tool_name = decision.tool_calls[0].tool_name if decision.tool_calls else None
        observation = turn.observation
        views.append(
            ControlTurnView(
                action_type=_action_type_text(decision.action_type),
                tool_name=tool_name,
                observation_success=observation.success if observation is not None else None,
                tool_arguments=decision.tool_calls[0].arguments if decision.tool_calls else None,
                observation_payload=observation.payload if observation is not None else None,
                observation_error=observation.error if observation is not None else None,
            )
        )
    return tuple(views)


def control_turns(state: AgentState) -> tuple[ControlTurnView, ...]:
    """Session projection when populated; otherwise in-process control cache."""
    projected = projected_control_turns(state)
    if projected:
        return projected
    return _history_control_turns(state)


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
        if turn.action_type != ActionType.USE_TOOL:
            break
        if turn.tool_name != tool_name:
            break
        count += 1
    return count


__all__ = [
    "ControlTurnView",
    "append_turn_control_fact",
    "consecutive_same_tool",
    "control_turns",
    "fold_control_turns_from_events",
    "iter_control_turns_reversed",
    "last_observation_success",
    "projected_control_turns",
]
