"""Tools Provider plugin — Tier-2 (tool factories)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols.runtime.infra import Tool
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    factories: list[str] = Field(default_factory=lambda: ["g2a"])


def _g2a_factory(run: object | None = None) -> list:
    from lca.infrastructure.tools.default_set import build_default_tools

    bind = run if isinstance(run, dict) else {}
    return build_default_tools(
        store=bind.get("file_store"),
        bindings=bind.get("bindings"),
        sandbox=bind.get("sandbox"),
        search=bind.get("search"),
        skill_store=bind.get("skill_store"),
        machine_resolver=bind.get("machine_resolver"),
        fallback=False,
    )


@plugin(
    id="lca-tools-provider",
    requires=["tools"],
    implements=[Tool],
    layer="L0",
    effects="tools",
    description="Register Tool factories on the ToolsService Definition (forked per-run).",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-tools-provider.checked', 'lca-tools-provider.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    if "g2a" in config.factories:
        ctx.require("tools").register_factory("g2a", _g2a_factory)
