"""ComponentRegistry seam definition — Tier-1 empty registry (ADR-0074).

Provides an empty ``ComponentRegistry`` under the ``component_registry``
capability key. Individual contributor plugins inject this registry and
register their specific component implementations, enabling per-component
substitution without replacing the entire aggregate.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import COMPONENT_REGISTRY
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-component-registry-seam",
    provides=[COMPONENT_REGISTRY.key],
    requires=[],
    layer="L4",
    kind=PluginKind.SEAM,
    effects="none",
    description="Provide an empty ComponentRegistry for contributor plugins to populate.",
    test_suite="tests/architecture/test_component_registry_seam.py",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    from lca.infrastructure.component_registry import ComponentRegistry

    ctx.provide(COMPONENT_REGISTRY.key, ComponentRegistry())


__all__ = ["Config", "setup"]
