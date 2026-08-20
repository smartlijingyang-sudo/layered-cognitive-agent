"""ToolLoopBreakerGate contribution — posts onto GateService."""

from __future__ import annotations
from pydantic import BaseModel
from lca.contracts.protocols import DecisionGate
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="gate.tool-loop-breaker",
    requires=["gates"],
    implements=[DecisionGate],
    layer="L1",
    effects="none",
    description="Break tool-call loops by switching action_type to respond.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.tool_loop_breaker import ToolLoopBreakerGate

    ctx.inject("gates").add(ToolLoopBreakerGate, id="tool-loop-breaker", slot="loop", order=20)
