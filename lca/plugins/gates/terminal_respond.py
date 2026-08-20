"""TerminalRespondGate plugin — named factory ``gate.terminal-respond``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.brain.decision_gates.terminal_respond import TerminalRespondGate


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="gate.terminal-respond")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named gate factory ``gate.terminal-respond``."""
    ctx.provide("gate.terminal-respond", TerminalRespondGate)
