"""phase.topology.bundle — declarative topology sourced from a bundle YAML.

ADR-0220 §3.4 P10: alternative topology provider that reads a Bundle Graph
v2 YAML (ADR-0217) and projects it into the same ``PhaseNode`` list shape
that the unified graph kernel expects. This replaces the legacy
``phase.topology.standard`` hand-written node list with the agent.run.phase
typed DTO graph, while preserving the compile path's invariants.

The plugin is factory-style: it accepts a ``plan_ref`` pointing at a
BundleGraphSpec YAML and exposes its nodes / edges as the active topology.
The framework's interpreter then enters the first node; nodes carrying
``sub_spec_ref`` are delegated to SubgraphRunner at runtime.

delete-when:
  N/A — this plugin is the new canonical topology source for agent-level
  compositions (ADR-0220 §3.4). It co-exists with
  ``phase.topology.standard`` for non-agent regions.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
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
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,  # noqa: F811
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Bundle-backed phase topology configuration.

    Attributes:
        plan_ref: Path to a BundleGraphSpec YAML file (relative to repo root).
        entry_node: Optional explicit entry node id; defaults to the first node.
    """

    model_config = ConfigDict(extra="forbid")
    plan_ref: str = Field(min_length=1)
    entry_node: str | None = None


SPEC = PluginSpec(
    api_version="lca/plugin-spec/v1",
    id="phase.topology.bundle",
    revision="1.0.0",
    kind=PluginSpecKind.PROVIDER,
    layer="L2",
    functional_group="G5",
    implementation=PluginImplementation(
        module="lca.plugins.loop.graph.topology.bundle.plugin",
        setup="setup",
    ),
    configuration=PluginConfiguration(
        schema="lca.plugins.loop.graph.topology.bundle.plugin.Config",
    ),
    provides=(
        CapabilityDeclaration(
            key="phase.topology.bundle",
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
    id="phase.topology.bundle",
    Config=Config,
    provides=("phase.topology.bundle",),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_topology_bundle.checked", "phase_topology_bundle.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Load a bundle YAML and publish its nodes as the active topology.

    Resolution is performed at setup time via ``_load_bundle_graph_spec``
    and ``_project_to_phase_graph``. Failures surface as
    ``DeclarativeValidationError`` from the subgraph_resolver module.
    """
    if not isinstance(config, Config):
        raise TypeError("phase.topology.bundle requires Config")

    from lca.harness.declarative.compile.subgraph_resolver import (
        _load_bundle_graph_spec,
    )

    spec = _load_bundle_graph_spec(config.plan_ref)
    nodes_payload = tuple(
        _project_node(n, config.entry_node) for n in spec.nodes
    )
    ctx.provide(
        "phase.topology.bundle",
        {
            "plan_ref": config.plan_ref,
            "entry_node": config.entry_node or spec.entry or spec.nodes[0].id,
            "nodes": nodes_payload,
        },
    )


def _project_node(n, entry_node: str | None) -> dict:
    """Project one BundleGraphNode into the topology-plugin node payload shape.

    Mirrors ``PhaseNodeConfig.model_dump(mode='json')`` output for
    compatibility with ``phase_graph_compiler``.
    """
    max_visits = int(n.config.get("max_visits", 1)) if n.config else 1
    node_region = n.region if n.region is not None else (n.region or "phase:agent")
    sub_spec_ref_payload = None
    if n.sub_spec_ref is not None:
        sub_spec_ref_payload = {
            "plan_ref": n.sub_spec_ref.plan_ref,
            "entry_node": n.sub_spec_ref.entry_node,
            "binding_edge": n.sub_spec_ref.binding_edge,
        }
    return {
        "id": n.id,
        "phase": "agent",
        "binding": n.factory,
        "max_visits": max_visits,
        "terminal": False,
        "entry": n.id == entry_node if entry_node else False,
        "precondition": None,
        "terminal_predicate": None,
        "sub_spec_ref": sub_spec_ref_payload,
    }


__all__ = ["SPEC", "Config", "setup"]
