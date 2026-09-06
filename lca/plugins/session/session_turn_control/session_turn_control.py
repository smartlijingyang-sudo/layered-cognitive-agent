"""TurnControlUnit — control-plane turn fold for gates/stop (ADR-0191 Wave C)."""

from __future__ import annotations

from typing import Any

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
