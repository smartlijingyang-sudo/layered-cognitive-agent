"""Profile provider for concurrent Session follow-up admission policy."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.session.session_turn import SessionFollowupPolicy
from lca.harness.agent.followup_policy import EnqueueFollowupPolicy, RejectFollowupPolicy
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Select the safe handling policy for a follow-up during an active turn."""

    mode: Literal["enqueue", "reject"] = "enqueue"
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-session-followup-policy",
    requires=[],
    provides=["session_followup_policy"],
    implements=[SessionFollowupPolicy],
    layer="L3",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide a pure, profile-selected policy for admitting follow-up messages "
        "while a Session turn is active."
    ),
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-session-followup-policy.checked", "lca-session-followup-policy.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("session_followup_policy",),
        emits=("session_followup_policy.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose one policy without coupling Session command routing to its mode."""

    policy: SessionFollowupPolicy = (
        EnqueueFollowupPolicy() if config.mode == "enqueue" else RejectFollowupPolicy()
    )
    ctx.provide("session_followup_policy", policy)


__all__ = ["Config", "setup"]
