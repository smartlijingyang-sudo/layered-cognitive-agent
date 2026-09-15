"""phase.think.history_assemble.history_derive — typed writer→model boundary.

think.history.assemble 图节点 1:从 ``RunSessionWriter`` 投影
``ModelVisibleRequest``(spec §D,ADR-0226 §4.1)。孤儿消息丢弃由
:meth:`RunSessionWriter.derive_messages` 在 writer 侧完成,本节点只做
typed-boundary adapter:state / writer → ModelVisibleRequest。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

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
from lca.framework.graph.nodes.history_assemble import history_assemble
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

if TYPE_CHECKING:
    from lca.contracts.protocols.session.model.context import ModelVisibleRequest


@dataclass(frozen=True, slots=True)
class HistoryAssembleExecutor:
    """think.history.assemble 节点 1:writer + state → ModelVisibleRequest."""

    semantic_name: str = "history.derive"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = ("state", "writer")
    declared_outputs: tuple[PortName, ...] = ("model_visible_request",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """history.derive 入口。

        inputs 端口(yaml):state (AgentState), writer (RunSessionWriterProtocol)
        outputs 端口(yaml):model_visible_request (ModelVisibleRequest)

        state 缺失时回退 ``context.runtime``(与 context_compose/collect
        一致);writer 为 None → TypeError(typed-boundary 守门人)。
        """
        state = input.port_values.get("state")
        if state is None:
            state = context.runtime.get("state") if hasattr(context, "runtime") else None
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "history.derive: 'state' port must be an AgentState "
                f"instance, got {type(state).__name__}"
            )
        writer = input.port_values.get("writer")
        if writer is None:
            writer = context.runtime.get("writer") if hasattr(context, "runtime") else None
        if writer is None:
            raise TypeError(
                "history.derive: 'writer' port must be a RunSessionWriterProtocol"
                " instance; got None"
            )
        result: ModelVisibleRequest = await history_assemble(state=state, writer=writer)
        return NodeOutput(port_values={"model_visible_request": result})


@plugin(
    id="phase.think.history_assemble.history_derive",
    Config=None,
    provides=("think::history.derive",),
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
                "phase_think_history_assemble_history_derive.checked",
                "phase_think_history_assemble_history_derive.served",
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
    executor = HistoryAssembleExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["HistoryAssembleExecutor", "setup"]
