"""State Store Provider plugin — profile-selected memory or SQLite backends."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from lca.contracts.protocols import StateStore
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    """Declare the StateStore implementations and active profile default."""

    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["memory"])
    active_provider: str = "memory"
    sqlite_database_path: str = ".lca/agent-state.db"


@plugin(
    id="lca-state-store-provider",
    requires=["state_store"],
    implements=[StateStore],
    layer="L0",
    effects="none",
    description="Register memory or durable SQLite StateStore providers selected by Profile.",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-state-store-provider.checked', 'lca-state-store-provider.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('plugin.serve',),
        emits=('plugin.served',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register configured StateStore factories and select the active provider."""

    from lca.infrastructure.state_store.in_memory_store import InMemoryStateStore
    from lca.infrastructure.state_store.sqlite_store import SqliteStateStore

    supported = {"memory", "sqlite"}
    requested = set(config.providers)
    unknown = requested - supported
    if unknown:
        raise ValueError(f"unsupported StateStore providers: {sorted(unknown)}")
    if config.active_provider not in requested:
        raise ValueError("active_provider must be included in providers")

    service = ctx.require("state_store")
    if "memory" in requested:
        service.register(
            "memory",
            InMemoryStateStore,
            activate=config.active_provider == "memory",
        )
    if "sqlite" in requested:
        database_path = Path(config.sqlite_database_path)
        service.register(
            "sqlite",
            lambda: SqliteStateStore(database_path),
            activate=config.active_provider == "sqlite",
        )


__all__ = ["Config", "setup"]
