"""InMemoryMiddlewareRegistry plugin — named factory ``middleware_registry.memory``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.mechanisms import HookRegistry
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_memory_middleware_registry(hooks: HookRegistry) -> object:
    from lca.harness.middleware import InMemoryMiddlewareRegistry
    from lca.layer2_runtime.hook_middleware import install_hook_bridge

    registry = InMemoryMiddlewareRegistry()
    install_hook_bridge(registry, hooks)
    return registry


@plugin(
    id="middleware_registry.memory",
    provides=["middleware_registry.memory"],
    layer="L1",
    effects="none",
    description="Provide the named middleware factory ``middleware_registry.memory``.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the named middleware factory ``middleware_registry.memory``."""
    ctx.provide("middleware_registry.memory", build_memory_middleware_registry)
