"""ToolLoopBreakerGate plugin — named factory ``gate.tool-loop-breaker``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.brain.decision_gates.tool_loop_breaker import ToolLoopBreakerGate


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="gate.tool-loop-breaker")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named gate factory ``gate.tool-loop-breaker``."""
    ctx.provide("gate.tool-loop-breaker", ToolLoopBreakerGate)
