"""phase.concept.role_snapshot.capability_role_compose — typed RoleSnapshot composer.

concept.role.snapshot 图节点 2:typed ``RoleProfile`` + ``TeamAwareness | None``
→ ``RoleSnapshot`` frozen boundary DTO(ADR-0220 §4.1)。

P3 骨架:直接拼装 typed ``RoleSnapshot(profile, team_awareness)``;无 duck-type
state 反射,无 inline 默认值创建;typed contract 由 boundary DTO 自己把关
(``extra="forbid"`` + ``frozen=True``)。
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
from lca.contracts.models.cognition.boundary import RoleSnapshot
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
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
class CapabilityRoleComposeExecutor:
    """concept.role.snapshot 节点 2:RoleProfile + TeamAwareness → RoleSnapshot."""

    semantic_name: str = "capability.role.compose"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("role", "team_awareness")
    declared_outputs: tuple[PortName, ...] = ("role_snapshot",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """capability.role.compose 入口。

        inputs 端口(yaml):role (RoleProfile), team_awareness (TeamAwareness | None)
        outputs 端口(yaml):role_snapshot (RoleSnapshot)

        ``role`` 由 ``capability.role.normalize`` 提供,``team_awareness``
        由 driver 从 runtime team 注入。None 是合法值(solo run)。
        """
        del context
        role = input.port_values.get("role")
        if not isinstance(role, RoleProfile):
            raise TypeError(
                "capability.role.compose: 'role' port must be a RoleProfile "
                f"instance, got {type(role).__name__}"
            )
        team_awareness = input.port_values.get("team_awareness")
        if team_awareness is not None and not isinstance(team_awareness, TeamAwareness):
            raise TypeError(
                "capability.role.compose: 'team_awareness' port must be a "
                f"TeamAwareness instance or None, got {type(team_awareness).__name__}"
            )
        role_snapshot = RoleSnapshot(profile=role, team_awareness=team_awareness)
        return NodeOutput(port_values={"role_snapshot": role_snapshot})


@plugin(
    id="phase.concept.role_snapshot.capability_role_compose",
    Config=None,
    provides=("concept::capability.role.compose",),
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
                "phase_concept_role_snapshot_capability_role_compose.checked",
                "phase_concept_role_snapshot_capability_role_compose.served",
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
    executor = CapabilityRoleComposeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["CapabilityRoleComposeExecutor", "setup"]
