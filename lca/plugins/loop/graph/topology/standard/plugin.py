"""Declarative provider for phase-node topology.

The selected Profile owns concrete node identities and execution metadata.  The
runtime compiler only validates and projects this immutable data; it does not
select an entry node, terminal node, or visit limit itself.
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


class PhaseNodeConfig(BaseModel):
    """One executable node declared by a topology provider."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    # Plan §13.11: phase_node 字段在 sub_spec_ref 节点上不再 required(节点
    # 由 interpreter 走子图驱动, 不调用 phase executor);其他节点保持
    # 必填以维持 PG-001 校验。运行期在 _compile_declared_node 拒绝
    # "无 binding 且无 sub_spec_ref" 组合。
    binding: str | None = Field(default=None, min_length=1)
    max_visits: int = Field(gt=0)
    terminal: bool = False
    entry: bool = False
    # PR-C (ADR-0214 §6.1): PG-007 三件套入口 / 出口谓词(可空字符串由
    # 编译器拒绝; None 表示未声明, 行为等价于历史)。
    precondition: str | None = None
    terminal_predicate: str | None = None
    # Node Note 2026-09-09-phase-node-sub-spec-ref: 节点级嵌套子图引用。
    # 与 ``PhaseEdge.subgraph_ref`` 同形 (plan_ref/entry_node/binding_edge),
    # 由 ``_compile_subgraph_ref`` 在 phase_graph_compiler 路径编译为
    # ``SubgraphReference(binding_edge=node.id)``。
    sub_spec_ref: dict | None = None


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
        module="lca.plugins.loop.graph.topology.standard.plugin",
        setup="setup",
    ),
    configuration=PluginConfiguration(
        schema="lca.plugins.loop.graph.topology.standard.plugin.Config",
    ),
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
    effects="none",
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
            descriptors=("phase_topology_standard.checked", "phase_topology_standard.served")
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
    """Expose immutable topology data; graph compilation remains harness-owned."""

    if not isinstance(config, Config):
        raise TypeError("phase topology plugin requires Config")
    ctx.provide(
        "phase.topology.standard",
        {"nodes": tuple(node.model_dump(mode="json") for node in config.nodes)},
    )


__all__ = ["SPEC", "Config", "PhaseNodeConfig", "setup"]
