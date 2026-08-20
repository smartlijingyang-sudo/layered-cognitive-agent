"""SimpleSafeExecutor plugin — named factory ``safe_executor.simple``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="safe_executor.simple")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named SafeExecutor factory ``safe_executor.simple``."""
    ctx.provide("safe_executor.simple", SimpleSafeExecutor)
