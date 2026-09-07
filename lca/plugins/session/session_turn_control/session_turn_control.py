"""TurnControlUnit — control-plane turn fold for gates/stop (ADR-0191 Wave C)."""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.session.control_state import ControlState, ControlTurn
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca_kernel.events.session.session import SessionEvent

__all__ = ["Config", "TurnControlUnit", "setup"]

_TURN_ENDED = "turn.ended.v1"
_TURN_CONTROL = "turn.control.v1"
_REDUCER_APPLY = "spine.runtime.reducer.apply"


class TurnControlUnit:
    """Fold turn/control markers from Session facts."""

    key = "turn_control"
    state_version = 1

    def init(self, header: Any) -> dict[str, Any]:
        del header
        return {"turns": [], "last_action_type": None, "last_tool_name": None}

    def apply(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        if event.type == _TURN_CONTROL:
            payload = event.data if isinstance(event.data, dict) else {}
            turns = [
                *state["turns"],
                {
                    "action_type": payload.get("action_type"),
                    "tool_name": payload.get("tool_name"),
                    "observation_success": payload.get("observation_success"),
                    "tool_arguments": payload.get("tool_arguments"),
                    "observation_payload": payload.get("observation_payload"),
                    "observation_error": payload.get("observation_error"),
                    "files_created": payload.get("files_created") or (),
                },
            ]
            return {
                **state,
                "turns": turns,
                "last_action_type": payload.get("action_type"),
                "last_tool_name": payload.get("tool_name"),
            }
        if event.type == _TURN_ENDED:
            turn = event.data.get("turn")
            if isinstance(turn, int) and not isinstance(turn, bool):
                turns = [*state["turns"], {"turn": turn, "reason": event.data.get("reason")}]
                return {**state, "turns": turns}
        if event.type == _REDUCER_APPLY:
            payload = event.data if isinstance(event.data, dict) else {}
            method = str(payload.get("method") or "")
            if method == "apply_turn":
                return {
                    **state,
                    "last_action_type": payload.get("action_type"),
                    "last_tool_name": payload.get("tool_name"),
                }
        return state

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state)

    def fold(self, session: Any) -> ControlState:
        """Build :class:`ControlState` directly from a Session snapshot.

        Implements :class:`TurnControlProjection` (ADR-0191 §C1). The
        fold is pure: it iterates ``session.snapshot_events()`` from
        empty state and never reads ``state.control_turns``. When
        ``session`` exposes no snapshot surface (cold/unbound path),
        returns an empty :class:`ControlState` — gates must treat empty
        projection as "no control signal" rather than fall back to
        in-process state.
        """
        snapshot = getattr(session, "snapshot_events", None)
        if not callable(snapshot):
            return ControlState()
        state = self.init(getattr(session, "header", None))
        for event in cast("Any", snapshot)():
            state = self.apply(state, event)
        return _state_to_control_state(state)


def _state_to_control_state(state: dict[str, Any]) -> ControlState:
    """Convert the internal fold state into the gate-facing view.

    Drops ``turn.ended.v1`` markers (``turn``/``reason`` keys): gates
    consume control summaries, not session-end markers — they were an
    internal fold input to advance the last-action cursor. Fold input
    facts stay in the event log; the view is the only projection
    surface gates read.
    """
    raw_turns = state.get("turns") or []
    turns: list[ControlTurn] = []
    for item in raw_turns:
        if not isinstance(item, dict):
            continue
        if "turn" in item:
            # ``turn.ended.v1`` marker: not a gate-facing control entry.
            continue
        tool_arguments = item.get("tool_arguments")
        if tool_arguments is not None and not isinstance(tool_arguments, dict):
            tool_arguments = None
        files_created = item.get("files_created") or ()
        if not isinstance(files_created, (list, tuple)):
            files_created = ()
        turns.append(
            ControlTurn(
                action_type=item.get("action_type"),
                tool_name=item.get("tool_name"),
                observation_success=item.get("observation_success"),
                tool_arguments=tool_arguments,
                observation_payload=item.get("observation_payload"),
                observation_error=item.get("observation_error"),
                files_created=tuple(str(x) for x in files_created),
            )
        )
    return ControlState(
        turns=tuple(turns),
        last_action_type=state.get("last_action_type"),
        last_tool_name=state.get("last_tool_name"),
    )


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.plugins.session.turn_control",
    Config=Config,
    provides=("session.projection.turn_control",),
    requires=("session.projections",),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    test_suite="tests/plugins/session/test_turn_control_projection.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION,
            control_slots=(),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("session.turn_control.checked", "session.turn_control.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    unit = TurnControlUnit()
    ctx.provide("session.projection.turn_control", unit)
    registry = ctx.soft_get("session.projections")
    if registry is None:
        return
    registry.register(unit)
