"""ComponentRegistry contributor: InMemoryStateStore (ADR-0074).

Injects the shared ComponentRegistry and registers the in-memory
state_store implementation under ComponentKind.STATE_STORE.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.enums import ComponentKind
from lca.contracts.capabilities import COMPONENT_REGISTRY
from lca.contracts.protocols.journal.spec import STATE_STORE_CHOICE_MEMORY
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-component-state-store-contributor",
    provides=[],
    requires=[COMPONENT_REGISTRY.key],
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register InMemoryStateStore into the shared ComponentRegistry.",
    test_suite="tests/architecture/test_component_registry_seam.py",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    from lca.infrastructure.state_store.in_memory_store import InMemoryStateStore

    registry = ctx.require(COMPONENT_REGISTRY.key)
    registry.register(ComponentKind.STATE_STORE, STATE_STORE_CHOICE_MEMORY, InMemoryStateStore)


__all__ = ["Config", "setup"]
