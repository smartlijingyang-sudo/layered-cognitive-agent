"""TerminalRespondGate contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="gate.terminal-respond",
    requires=["gates"],
    implements=[DecisionGate],
    layer="L1",
    effects="none",
    description="Convert the terminal action_type to a structured respond.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G6_DECISION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.THINK_GUARD,
        scope=Scope.TURN,
        authority=("decision.read", "decision.rewrite"),
        evidence=("gate.terminal-respond.enforced",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.brain.decision_gates.terminal_respond import TerminalRespondGate

    ctx.require("gates").add(TerminalRespondGate, id="terminal-respond", slot="loop", order=40)
