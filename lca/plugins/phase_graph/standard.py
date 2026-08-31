"""Declarative provider for phase-node topology.

The selected Profile owns concrete node identities and execution metadata.  The
runtime compiler only validates and projects this immutable data; it does not
select an entry node, terminal node, or visit limit itself.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
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
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class PhaseNodeConfig(BaseModel):
    """One executable node declared by a topology provider."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    binding: str = Field(min_length=1)
    max_visits: int = Field(gt=0)
    terminal: bool = False
    entry: bool = False


class Config(BaseModel):
    """Phase-node topology supplied by the selected Profile or Bundle."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[PhaseNodeConfig] = Field(default_factory=list)


SPEC = PluginSpec(
    api_version="lca/plugin-spec/v1",
    id="phase.topology.standard",
    revision="1.0.0",
    kind=PluginSpecKind.PROVIDER,
    layer="L2",
    functional_group="G5",
    implementation=PluginImplementation(
        module="lca.plugins.phase_graph.standard",
        setup="setup",
    ),
    configuration=PluginConfiguration(schema="lca.plugins.phase_graph.standard.Config"),
    provides=(
        CapabilityDeclaration(
            key="phase.topology.standard",
            cardinality="one",
            protocol="PhaseNode",
            scope="profile",
        ),
    ),
    requires=(),
    effects=("none",),
    ownership=OwnershipDeclaration(state_mutation="forbidden"),
    lifecycle=LifecycleDeclaration(
        scopes=("profile", "run"), activation="true", disposal="required"
    ),
    relations=(),
    evidence=EvidenceDeclaration(emits=("PhaseTopologyDeclared",), replay="required"),
    verification=VerificationDeclaration(
        test_suite="tests/declarative/test_phase_graph.py",
        properties=("declared_nodes", "single_entry", "explicit_node_limits"),
    ),
)


@plugin(
    id="phase.topology.standard",
    Config=Config,
    provides=("phase.topology.standard",),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("phase_topology_standard.checked", "phase_topology_standard.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Expose immutable topology data; graph compilation remains harness-owned."""

    if not isinstance(config, Config):
        raise TypeError("phase topology plugin requires Config")
    ctx.provide(
        "phase.topology.standard",
        {"nodes": tuple(node.model_dump(mode="json") for node in config.nodes)},
    )


__all__ = ["SPEC", "Config", "PhaseNodeConfig", "setup"]
