"""Skills Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.memory.operational_skills import SkillPackageInstaller
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["disk"])


@plugin(
    id="lca-skills-provider",
    requires=["skills"],
    implements=[SkillPackageInstaller],
    layer="L0",
    # materialize_bundled_skills() install_packages every repo skills/ pack
    # into the global store root. The filesystem effect is declared here so the
    # write stays visible to the effects audit (71515dace: an undeclared write
    # let a unit test rewrite the production ~/.lca/skills undetected).
    effects="filesystem",
    description="Register SkillPackageInstaller providers on the SkillsService Definition.",
    test_suite="tests/scenario/plugin/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-skills-provider.checked", "lca-skills-provider.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.skills.factory.factory import (
        materialize_bundled_skills,
        resolve_skill_store,
    )

    if "disk" in config.providers:
        store = resolve_skill_store()
        # RA-058:显式 boot 步骤（纯 resolve 不再写盘）。
        materialize_bundled_skills(store)
        ctx.require("skills").register("disk", store)
