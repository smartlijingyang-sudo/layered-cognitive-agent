"""ToolLoopBreakerGate contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import DecisionGate
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="gate.tool-loop-breaker",
    requires=["gates"],
    implements=[DecisionGate],
    layer="guard",
    side_effects="none",
    policy_class="control",
    description="Break tool-call loops by switching action_type to respond.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.tool_loop_breaker import ToolLoopBreakerGate

    ctx.inject("gates").add(ToolLoopBreakerGate, id="tool-loop-breaker", slot="loop", order=20)
