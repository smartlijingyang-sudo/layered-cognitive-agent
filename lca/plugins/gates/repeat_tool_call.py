"""RepeatToolCallGate contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import DecisionGate
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="gate.repeat-tool-call",
    requires=["gates"],
    implements=[DecisionGate],
    layer="L1",
    effects="none",
    description="Block runaway repeat-tool-call loops.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.repeat_tool_call import RepeatToolCallGate

    ctx.inject("gates").add(RepeatToolCallGate, id="repeat-tool-call", slot="loop", order=10)
