"""JournalStore factory registry plugin (Tier-1) —— ADR-0063 PR-8.

声明 ``journal_store_factories`` 注册中心；boot 后 ``providers/journal_store`` 把
``InMemoryJournalStore`` factory 注入。文件 backed 实现由后续 PR-8-ext 落地。

注：``journal_store`` 能力键已由 ``lca-journal-store`` (PR 已有插件) 持有 RunStore
类引用；本插件与之正交，注册的是 backend 工厂而非类。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-journal-store-factory-registry",
    provides=["journal_store_factories"],
    implements=None,  # type: ignore[arg-type]
    layer="L0",
    effects="none",
    description="Provide the JournalStoreBackend factory registry (PR-8).",
    test_suite="tests/test_journal_store_backend.py::test_factory_registry_provided",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-journal-store-factory-registry.checked', 'lca-journal-store-factory-registry.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("journal_store_factories", NamedRegistry())
