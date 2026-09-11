"""phase.concept.context_compose.context_skills_merge — typed ReasonerContext composer.

concept.context.compose 图节点 2:typed ``ContextManifest`` + ``task`` +
``activated_skills`` → ``ReasonerContext`` frozen boundary DTO
(ADR-0220 §4.1)。

P3 骨架:typed 拼装 ``ReasonerContext(task, activated_skills, manifest)``;
``activated_skills`` 来自 ``state.activated_skills``(Reducer-owned list),
转 tuple 满足 boundary frozen contract。不读 state 私有属性。
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
from lca.contracts.models.cognition.boundary import ReasonerContext
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.core.workspace.activation import ActivatedSkill
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
class ContextSkillsMergeExecutor:
    """concept.context.compose 节点 2:manifest + task + skills → ReasonerContext."""

    semantic_name: str = "context.skills.merge"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("manifest", "task", "state")
    declared_outputs: tuple[PortName, ...] = ("context",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """context.skills.merge 入口。

        inputs 端口(yaml):manifest (ContextManifest | None),
        task (str), state (AgentState)
        outputs 端口(yaml):context (ReasonerContext)
        """
        del context
        manifest = input.port_values.get("manifest")
        if manifest is not None and not isinstance(manifest, ContextManifest):
            raise TypeError(
                "context.skills.merge: 'manifest' port must be a "
                f"ContextManifest instance or None, got {type(manifest).__name__}"
            )
        task = input.port_values.get("task", "")
        if not isinstance(task, str):
            raise TypeError(
                "context.skills.merge: 'task' port must be a str "
                f"instance, got {type(task).__name__}"
            )
        state = input.port_values.get("state")
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "context.skills.merge: 'state' port must be an AgentState "
                f"instance or None, got {type(state).__name__}"
            )
        activated_skills: tuple[ActivatedSkill, ...] = ()
        if state is not None:
            activated_skills = tuple(state.activated_skills)
        if state is not None and not task and state.task:
            task = state.task
        reasoner_context = ReasonerContext(
            task=task,
            activated_skills=activated_skills,
            manifest=manifest,
        )
        return NodeOutput(port_values={"context": reasoner_context})


@plugin(
    id="phase.concept.context_compose.context_skills_merge",
    Config=None,
    provides=("concept::context.skills.merge",),
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
                "phase_concept_context_compose_context_skills_merge.checked",
                "phase_concept_context_compose_context_skills_merge.served",
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
    executor = ContextSkillsMergeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ContextSkillsMergeExecutor", "setup"]
