"""Langfuse JournalProjector factory plugin (Tier-2) —— 占位实现。

把 Langfuse 读者注册为 ``fact_readers`` 的 factory；真实实现复用
``lca/infrastructure/observability/exporters/langfuse.py``（之后 PR 重构）。
当前返回 no-op reader：保证 boot 链路通畅，不引入额外网络副作用。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.protocols import JournalProjector
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _NoopReader:
    """Langfuse placeholder：on_event/flush/close 全部空实现。"""

    def on_event(self, stamped: StampedEvent) -> None:
        return None

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


@plugin(
    id="lca-fact-reader-langfuse-factory",
    requires=["fact_readers"],
    implements=[JournalProjector],
    layer="L0",
    effects="network",
    description="Register Langfuse reader factory as fact_readers['langfuse'] (no-op placeholder).",
    test_suite="tests/test_fact_reader_plugin.py::test_provider_registers_langfuse_reader",
    kind=PluginKind.PROVIDER,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-fact-reader-langfuse-factory.checked', 'lca-fact-reader-langfuse-factory.served'),
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

    registry: NamedRegistry = ctx.require("fact_readers")

    def _make_langfuse_reader(
        settings: ObservabilitySettings | None = None, **_: Any
    ) -> JournalProjector:
        # 真实实现待 exporters/langfuse 迁移完成后替换；当前保留 no-op 以保 boot 链通畅。
        _ = settings
        return _NoopReader()

    registry.register("langfuse", _make_langfuse_reader)
