"""Journal seam plugin (Tier-1).

声明 ``journal_backends`` 注册中心；boot 后 ``providers/journal_memory`` 把
``MemoryJournal`` factory 注入。新增 journal backend = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.observability.ports import JournalBackend
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-journal-seam",
    provides=["journal_backends"],
    implements=[JournalBackend],
    layer="L0",
    effects="none",
    description="Provide the journal_backends seam (facade plugin-ification).",
    test_suite="tests/test_journal_plugin.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-journal-seam.checked', 'lca-journal-seam.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('journal_backends',),
        emits=('journal_backends.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("journal_backends", NamedRegistry())
