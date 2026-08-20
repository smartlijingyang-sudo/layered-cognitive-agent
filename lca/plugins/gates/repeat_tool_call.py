"""RepeatToolCallGate plugin — named factory ``gate.repeat-tool-call``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.brain.decision_gates.repeat_tool_call import RepeatToolCallGate


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="gate.repeat-tool-call")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named gate factory ``gate.repeat-tool-call``."""
    ctx.provide("gate.repeat-tool-call", RepeatToolCallGate)
