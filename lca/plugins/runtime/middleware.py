"""InMemoryMiddlewareRegistry plugin — named factory ``middleware_registry.memory``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.contracts.mechanisms import HookRegistry
from lca.harness.middleware import InMemoryMiddlewareRegistry
from lca.layer2_runtime.hook_middleware import install_hook_bridge


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_memory_middleware_registry(hooks: HookRegistry) -> InMemoryMiddlewareRegistry:
    registry = InMemoryMiddlewareRegistry()
    install_hook_bridge(registry, hooks)
    return registry


@plugin(name="middleware_registry.memory")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named middleware factory ``middleware_registry.memory``."""
    ctx.provide("middleware_registry.memory", build_memory_middleware_registry)
