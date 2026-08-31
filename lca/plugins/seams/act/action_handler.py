"""ActionHandlerRegistry Seam Definition plugin — Tier-1."""

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
    id="lca-action-handler-registry-seam",
    provides=["action_handler_registry"],
    requires=[],
    implements=["ActionHandlerRegistry"],
    layer="L1",
    effects="none",
    description="Provide the ActionHandlerRegistry Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-action-handler-registry-seam.checked', 'lca-action-handler-registry-seam.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.act.action_handlers import InMemoryActionHandlerRegistry

    # 接缝只提供中性能力容器；默认 handler 由独立 provider 统一安装。
    ctx.provide("action_handler_registry", InMemoryActionHandlerRegistry())


__all__ = ["setup"]
