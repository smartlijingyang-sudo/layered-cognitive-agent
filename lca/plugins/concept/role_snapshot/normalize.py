"""phase.concept.role_snapshot.capability_role_normalize — typed RoleProfile passthrough.

concept.role.snapshot 图节点 1:typed ``RoleProfile`` → normalized ``RoleProfile``
(ADR-0220 §4.1)。P3 骨架:RoleProfile 已是 frozen dataclass,
规范化是 no-op (透传);后续 P5+ 可在此节点加 normalization 规则
(字段 fallback / defaults),但不破坏 typed contract。
"""

from __future__ import annotations

from dataclasses import dataclass

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
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class CapabilityRoleNormalizeExecutor:
    """concept.role.snapshot 节点 1:typed RoleProfile passthrough."""

    semantic_name: str = "capability.role.normalize"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("role_profile",)
    declared_outputs: tuple[PortName, ...] = ("role",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """capability.role.normalize 入口。

        inputs 端口(yaml):role_profile (RoleProfile)
        outputs 端口(yaml):role (RoleProfile, normalized)

        P3 no-op:RoleProfile 已是 frozen dataclass,直接透传。
        """
        del context
        role_profile = input.port_values.get("role_profile")
        if not isinstance(role_profile, RoleProfile):
            raise TypeError(
                "capability.role.normalize: 'role_profile' port must be a "
                f"RoleProfile instance, got {type(role_profile).__name__}"
            )
        return NodeOutput(port_values={"role": role_profile})


@plugin(
    id="phase.concept.role_snapshot.capability_role_normalize",
    Config=None,
    provides=("concept::capability.role.normalize",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_concept_role_snapshot_capability_role_normalize.checked",
                "phase_concept_role_snapshot_capability_role_normalize.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = CapabilityRoleNormalizeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["CapabilityRoleNormalizeExecutor", "setup"]
