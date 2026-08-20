"""SimpleSafeExecutor plugin — named factory ``safe_executor.simple``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.infra import SafeExecutor
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="safe_executor.simple",
    provides=["safe_executor.simple"],
    implements=[SafeExecutor],
    layer="L1",
    effects="tools",
    description="Provide the SafeExecutor factory used by the Composer.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the named SafeExecutor factory ``safe_executor.simple``."""
    from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor

    ctx.provide("safe_executor.simple", SimpleSafeExecutor)
