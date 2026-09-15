"""phase.concept.context_compose.context_lines_collect — typed manifest passthrough.

concept.context.compose 图节点 1:从 ``AgentState.perceive`` 读
``ContextManifest``(typed boundary),typed 透传到下一节点
(ADR-0220 §4.1)。P3 骨架:仅做 typed 校验,不做 manifest 收集;
真实 manifest 装配由 perceive graph 在 P2 入口完成(perception projection)。
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
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState
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
class ContextLinesCollectExecutor:
    """concept.context.compose 节点 1:state.perceive → manifest."""

    semantic_name: str = "context.lines.collect"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("state",)
    declared_outputs: tuple[PortName, ...] = ("manifest",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """context.lines.collect 入口。

        inputs 端口(yaml):state (AgentState)
        outputs 端口(yaml):manifest (ContextManifest | None)

        P3 阶段:从 ``state.perceive`` 读 manifest。state 不存在时返 None。
        真实 manifest 收集发生在 perceive 阶段,本节点只做 typed 透传。
        """
        state = input.port_values.get("state")
        if state is None:
            state = context.runtime.get("state") if hasattr(context, "runtime") else None
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "context.lines.collect: 'state' port must be an AgentState "
                f"instance, got {type(state).__name__}"
            )
        manifest: ContextManifest | None = None
        if state is not None and state.perceive is not None:
            manifest = state.perceive.manifest
        return NodeOutput(port_values={"manifest": manifest})


@plugin(
    id="phase.concept.context_compose.context_lines_collect",
    Config=None,
    provides=("concept::context.lines.collect",),
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
                "phase_concept_context_compose_context_lines_collect.checked",
                "phase_concept_context_compose_context_lines_collect.served",
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
    executor = ContextLinesCollectExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ContextLinesCollectExecutor", "setup"]
