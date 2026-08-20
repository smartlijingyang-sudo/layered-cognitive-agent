"""RepeatToolCallGate plugin — named factory ``gate.repeat-tool-call``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import DecisionGate
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="gate.repeat-tool-call",
    provides=["gate.repeat-tool-call"],
    implements=[DecisionGate],
    layer="guard",
    side_effects="none",
    policy_class="control",
    description="Block runaway repeat-tool-call loops.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named gate factory ``gate.repeat-tool-call``."""
    from lca.layer1_cognitive.brain.decision_gates.repeat_tool_call import RepeatToolCallGate

    ctx.provide("gate.repeat-tool-call", RepeatToolCallGate)
