"""ToolLoopBreakerGate contribution — posts onto GateService (ADR-0074 PR-2)."""

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


# PR-2: typed control + functional_group + logic_address
_TOOL_LOOP_BREAKER_CONTROL: tuple[dict, ...] = (
    {
        "slot": ControlSlot.THINK_GUARD.value,
        "order": 20,
        "aggregation": "decision_priority",
        "failure_mode": "deny",
        "effect_class": "none",
        "reads": ["history.tool_signature_count"],
        "emits": ["policy.gate.tool-loop-breaker.denied"],
        "authority": ("gates.read",),
    },
)


@plugin(
    id="gate.tool-loop-breaker",
    requires=["gates"],
    implements=[DecisionGate],
    layer="L1",
    effects="none",
    description="Break tool-call loops by switching action_type to respond.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    control=_TOOL_LOOP_BREAKER_CONTROL,
    functional_group=FunctionalGroup.G6_DECISION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.THINK_GUARD,
        scope=Scope.TURN,
        authority=("gates.read",),
        evidence=("policy.gate.tool-loop-breaker.denied",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.tool_loop_breaker import ToolLoopBreakerGate

    ctx.inject("gates").add(ToolLoopBreakerGate, id="tool-loop-breaker", slot="loop", order=20)
