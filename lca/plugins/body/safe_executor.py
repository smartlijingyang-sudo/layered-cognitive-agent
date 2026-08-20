"""SimpleSafeExecutor plugin — named factory ``safe_executor.simple``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.infra import SafeExecutor
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="safe_executor.simple",
    provides=["safe_executor.simple"],
    implements=[SafeExecutor],
    layer="behavior",
    side_effects="tools",
    policy_class="control",
    description="Provide the SafeExecutor factory used by the Composer.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named SafeExecutor factory ``safe_executor.simple``."""
    from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor

    ctx.provide("safe_executor.simple", SimpleSafeExecutor)
