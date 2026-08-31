"""Skills Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols.memory.operational_skills import SkillPackageInstaller
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["disk"])


@plugin(
    id="lca-skills-provider",
    requires=["skills"],
    implements=[SkillPackageInstaller],
    layer="L0",
    effects="none",
    description="Register SkillPackageInstaller providers on the SkillsService Definition.",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-skills-provider.checked', 'lca-skills-provider.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.skills.factory import resolve_skill_store

    if "disk" in config.providers:
        ctx.require("skills").register("disk", resolve_skill_store())
