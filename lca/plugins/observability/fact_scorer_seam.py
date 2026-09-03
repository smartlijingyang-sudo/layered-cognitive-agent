"""Fact scorer seam plugin (Tier-1).

声明 ``fact_scorers`` 注册中心；boot 后 ``providers/fact_scorer`` 把各种
``ScorerFn`` factory 注入。新增 fact scorer = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-fact-scorer-seam",
    provides=["fact_scorers"],
    layer="L0",
    effects="none",
    description="Provide the fact_scorers seam (facade plugin-ification).",
    test_suite="tests/test_fact_scorer_plugin.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-fact-scorer-seam.checked", "lca-fact-scorer-seam.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("fact_scorers",),
        emits=("fact_scorers.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("fact_scorers", NamedRegistry())
