"""Declarative provider for the default ADR-0075 phase topology."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    CapabilityDeclaration,
    EvidenceDeclaration,
    LifecycleDeclaration,
    OwnershipDeclaration,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    VerificationDeclaration,
)
from lca.contracts.protocols.declarative.declarative_plugin import (
    OwnershipDeclaration,  # noqa: F811
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Phase topology supplied by the selected Profile or Bundle."""

    model_config = ConfigDict(extra="forbid")
    edges: list[dict[str, object]] = Field(default_factory=list)
    approval_resume_node: str | None = None


SPEC = PluginSpec(
    api_version="lca/plugin-spec/v1",
    id="phase.edge.standard",
    revision="1.0.0",
    kind=PluginSpecKind.PROVIDER,
    layer="L2",
    functional_group="G5",
    implementation=PluginImplementation(
        module="lca.plugins.phase_graph.edges_standard", setup="setup"
    ),
    configuration=PluginConfiguration(schema="lca.plugins.phase_graph.edges_standard.Config"),
    provides=(
        CapabilityDeclaration(
            key="phase.edge.standard", cardinality="one", protocol="PhaseEdge", scope="profile"
        ),
    ),
    requires=(),
    effects=("none",),
    ownership=OwnershipDeclaration(state_mutation="forbidden"),
    lifecycle=LifecycleDeclaration(
        scopes=("profile", "run"), activation="true", disposal="required"
    ),
    relations=(),
    evidence=EvidenceDeclaration(emits=("PhaseGraphDeclared",), replay="required"),
    verification=VerificationDeclaration(
        test_suite="tests/declarative/test_phase_graph.py",
        properties=("declared_topology", "bounded_reentry"),
    ),
)


@plugin(
    id="phase.edge.standard",
    Config=Config,
    provides=("phase.edge.standard",),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_edge_standard.checked", "phase_edge_standard.served")
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
    """Expose the selected edge declarations as data; execution remains MTK-owned."""

    ctx.provide(
        "phase.edge.standard",
        {
            "edges": tuple(config.edges),
            "approval_resume_node": config.approval_resume_node,
        },
    )


__all__ = ["SPEC", "Config", "setup"]
