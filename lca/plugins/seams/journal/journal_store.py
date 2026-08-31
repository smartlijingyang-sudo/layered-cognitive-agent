"""Journal store plugin — named factory ``journal_store``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-journal-store",
    provides=["journal_store"],
    layer="L1",
    effects="none",
    description="Provide RunStore class as ``journal_store``; Composer instantiates per-run.",
    test_suite="tests/test_plugin_alignment.py::test_compose_root_no_inline_instantiation",
    kind=PluginKind.PRIMITIVE,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-journal-store.checked", "lca-journal-store.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("journal_store",),
        emits=("journal_store.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the RunStore class as ``journal_store``.

    Composer instantiates a RunStore per-run; this plugin only registers
    the class so composition can resolve it without importing layer0.
    """
    from lca.infrastructure.observability import RunStore

    ctx.provide("journal_store", RunStore)
