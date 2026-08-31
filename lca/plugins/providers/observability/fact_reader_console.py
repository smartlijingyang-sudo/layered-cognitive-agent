"""ConsoleJournalProjector factory plugin (Tier-2).

把 ``ConsoleJournalProjector`` 注册为 ``fact_readers`` 的 factory。
人类视图场景卡 + 角色叙事 + Run Card + 序列图。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols import JournalProjector
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-fact-reader-console-factory",
    requires=["fact_readers"],
    implements=[JournalProjector],
    layer="L0",
    effects="none",
    description="Register ConsoleJournalProjector factory as fact_readers['console'].",
    test_suite="tests/test_fact_reader_plugin.py::test_provider_registers_console_reader",
    kind=PluginKind.PROVIDER,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-fact-reader-console-factory.checked', 'lca-fact-reader-console-factory.served'),
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
    from lca.infrastructure.observability import NamedRegistry, ObservabilitySettings
    from lca.infrastructure.observability.journal.console.projector import (
        ConsoleJournalProjector,
    )

    registry: NamedRegistry = ctx.require("fact_readers")

    def _make_console(settings: ObservabilitySettings | None = None, **_: Any) -> JournalProjector:
        cfg = settings or ObservabilitySettings()
        return ConsoleJournalProjector(verbosity=cfg.verbosity)

    registry.register("console", _make_console)
