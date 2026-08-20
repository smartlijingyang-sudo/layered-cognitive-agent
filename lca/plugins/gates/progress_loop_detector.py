"""ProgressLoopDetector plugin — named factory ``gate.progress-loop-detector``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.brain.decision_gates.progress_loop_detector import ProgressLoopDetector


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="gate.progress-loop-detector")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named gate factory ``gate.progress-loop-detector``."""
    ctx.provide("gate.progress-loop-detector", ProgressLoopDetector)
