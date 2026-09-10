"""phase.think.reason.plan — pure pre-render turn metadata.

think.reason inner_graph 第 1 节点 plugin:调 ``Reasoner.build_turn_plan``
算 plan,不调 LLM、不感知 EP。``requires=("reasoner",)`` 通过 Cordis 校验,
运行时从 ``context.runtime.reasoner`` 拿 capability 实例。

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
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ThinkReasonPlanExecutor:
    """think.reason inner_graph 第 1 节点:从 state 算 ReasonerTurnPlan。"""

    semantic_name: str = "think.reason.plan"
    region: str = "phase:think"

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think.reason.plan 入口。

        inputs 端口(yaml):(无)
        outputs 端口(yaml):turn_plan
        """
        runtime = context.runtime
        state = runtime.state
        reasoner = runtime.reasoner

        if reasoner is None or state is None:
            return NodeOutput(port_values={})

        # Duck-typed: ``Reasoner.build_turn_plan`` is optional in some
        # implementations; fail-soft if absent (e.g. legacy reasoner).
        build_turn_plan = getattr(reasoner, "build_turn_plan", None)
        if not callable(build_turn_plan):
            return NodeOutput(port_values={})
        plan = build_turn_plan(state)
        return NodeOutput(port_values={"turn_plan": plan})


@plugin(
    id="phase.think.reason.plan",
    Config=None,
    provides=("phase.think.reason.plan",),
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
                "phase_think_reason_plan.checked",
                "phase_think_reason_plan.served",
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
    executor = ThinkReasonPlanExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkReasonPlanExecutor", "setup"]
