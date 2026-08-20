"""TerminalRespondGate contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import DecisionGate
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
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.terminal_respond import TerminalRespondGate

    ctx.inject("gates").add(TerminalRespondGate, id="terminal-respond", slot="loop", order=40)
