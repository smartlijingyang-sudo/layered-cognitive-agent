"""phase.think.reason.render — pure post-render turn metadata.

think.reason inner_graph 第 2 节点 plugin:调 ``Reasoner.render_turn``
从 (state, plan) 算 render,不调 LLM、不感知 EP。``requires=("reasoner",)``
通过 Cordis 校验,运行时从 ``context.runtime.reasoner`` 拿 capability 实例。

ADR-0218 §3.3:节点 plugin 由作者显式书写完整 ``@plugin(...)`` 装饰器,
工厂 ``setup(ctx)`` 通过 Cordis ``ctx.provide`` 单键注册 composite key。
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
class ThinkReasonRenderExecutor:
    """think.reason inner_graph 第 2 节点:从 (state, plan) 算 ReasonerTurnRender。"""

    semantic_name: str = "think.reason.render"
    region: str = "phase:think"
    # ADR-0219 §5.5: typed port contract declared on the plugin (graph
    # layer does not know port names; it only knows topology).
    declared_inputs: tuple[PortName, ...] = ("turn_plan",)
    declared_outputs: tuple[PortName, ...] = ("turn_render",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think.reason.render 入口。

        inputs 端口(yaml):turn_plan
        outputs 端口(yaml):turn_render
        """
        runtime = context.runtime
        state = runtime.state
        reasoner = runtime.reasoner
        plan = input.port_values.get("turn_plan")

        if reasoner is None or state is None or plan is None:
            return NodeOutput(port_values={})

        # Duck-typed: fail-soft if absent.
        render_turn = getattr(reasoner, "render_turn", None)
        if not callable(render_turn):
            return NodeOutput(port_values={})
        render = render_turn(state, plan)
        return NodeOutput(port_values={"turn_render": render})


@plugin(
    id="phase.think.reason.render",
    Config=None,
    provides=("phase:think::think.reason.render",),
    requires=("reasoner",),
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
                "phase_think_reason_render.checked",
                "phase_think_reason_render.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "reasoner"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = ThinkReasonRenderExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkReasonRenderExecutor", "setup"]
