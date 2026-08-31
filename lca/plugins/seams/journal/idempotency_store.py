"""Durable effect idempotency capability seam."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols.journal.idempotency import IdempotencyStore
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    """Filesystem location for the runtime receipt database."""

    model_config = {"extra": "forbid"}
    path: str = Field(default="traces/runtime/idempotency.sqlite3", min_length=1)


@plugin(
    id="lca-idempotency-store-seam",
    provides=["idempotency_store"],
    implements=[IdempotencyStore],
    layer="L2",
    effects="filesystem",
    description="Provide the durable effect claim and receipt store for declarative runtime execution.",
    test_suite="tests/runtime/test_idempotency_store.py",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-idempotency-store-seam.checked', 'lca-idempotency-store-seam.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('idempotency_store',),
        emits=('idempotency_store.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.idempotency_store import SqliteIdempotencyStore

    ctx.provide("idempotency_store", SqliteIdempotencyStore(config.path))


__all__ = ["Config", "setup"]
