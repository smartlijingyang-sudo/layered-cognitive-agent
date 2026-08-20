"""TerminalRespondGate contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import DecisionGate
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="gate.terminal-respond",
    requires=["gates"],
    implements=[DecisionGate],
    layer="guard",
    side_effects="none",
    policy_class="control",
    description="Convert the terminal action_type to a structured respond.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.terminal_respond import TerminalRespondGate

    ctx.inject("gates").add(TerminalRespondGate, id="terminal-respond", slot="loop", order=40)
