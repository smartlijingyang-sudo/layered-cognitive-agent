"""Tools Compose Service plugin — named factory ``tools.compose_service``.

Returns a fresh :class:`ToolsService` per composition. The Composer no
longer instantiates ``ToolsService()`` inline; it resolves a factory
through this plugin (``ctx.require("tools.compose_service")()``).
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.runtime.infra import ToolRegistry
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_tools_service_compose() -> ToolRegistry:
    from lca.infrastructure.capability.tools import ToolsService

    return ToolsService()


@plugin(
    id="tools.compose_service",
    provides=["tools.compose_service"],
    requires=[],
    implements=[ToolRegistry],
    layer="L1",
    effects="tools",
    description="Compose-time ToolsService factory (one fresh instance per compose).",
    test_suite="tests/test_plugin_alignment.py::test_compose_root_no_inline_instantiation",
    kind=PluginKind.PRIMITIVE,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('tool.invoke',),
        evidence=('tools_compose_service.checked', 'tools_compose_service.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the named factory ``tools.compose_service``."""
    ctx.provide("tools.compose_service", build_tools_service_compose)
