"""phase.concept.act_subgraph.act_observe_terminate_decide — typed should_terminate decision.

``concept.act_subgraph`` 内嵌节点:``EffectReceipt`` →
``EffectReceipt`` + ``should_terminate``(纯路由决策)。

PR-3 split:本节点从原 ``act.observe`` 中剥离 ``should_terminate`` 决策,
使 ``act.observe`` 节点只承担 receipt 归一化 + RunFact commit(由同级
``act.observe.commit_fact`` 节点承担),节点职责符合 AGENTS.md §2.2
「事实源 ≠ 决策」分类。

决策规则(从原 ``act.observe`` 段平移,确定性 + 幂等):

    should_terminate = (
        receipt.failure_kind == FAILURE_KIND_EXECUTION
        or (receipt.failure_kind is None and receipt.outcome.value == "failed")
    )

无副作用:不调 journal,不调 Body / Registry / SafeExecutor,不构造 envelope。
typed-port 边界:输入 ``receipt``、输出 ``receipt`` + ``should_terminate``。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.atoms.semantic.keys import FAILURE_KIND_EXECUTION
from lca.contracts.harness.act.effect_receipt import EffectReceipt
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
class ActObserveTerminateDecideExecutor:
    """``concept.act_subgraph`` 节点:EffectReceipt → EffectReceipt + should_terminate。

    Pure routing decision — no journal writes, no Body dispatch, no capability
    reads. Reads ``receipt`` port, emits ``receipt`` (passthrough) + a bool
    ``should_terminate`` port that the outer driver reads via typed-port
    boundary to route the next edge.
    """

    semantic_name: str = "act.observe.terminate_decide"
    region: str = "act"
    declared_inputs: tuple[PortName, ...] = ("receipt",)
    declared_outputs: tuple[PortName, ...] = ("receipt", "should_terminate")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.observe.terminate_decide 入口。

        inputs 端口(yaml): receipt (EffectReceipt)
        outputs 端口(yaml): receipt (EffectReceipt, passthrough),
                            should_terminate (bool)

        决策规则:deterministic-failure shortcut 当 ``failure_kind ==
        execution`` 或 pre-classifier ``outcome == failed`` 时,emit
        ``should_terminate=True``;其他情况 ``False``(包括 transient /
        validation / tool_wire 等可重试失败)。
        """
        del context  # unused: pure function of input port value
        receipt = input.port_values.get("receipt")
        if not isinstance(receipt, EffectReceipt):
            raise TypeError(
                "act.observe.terminate_decide: 'receipt' port must be an "
                f"EffectReceipt instance, got {type(receipt).__name__}"
            )

        should_terminate = receipt.failure_kind == FAILURE_KIND_EXECUTION or (
            receipt.failure_kind is None and receipt.outcome.value == "failed"
        )

        return NodeOutput(
            port_values={
                "receipt": receipt,
                "should_terminate": should_terminate,
            }
        )


@plugin(
    id="phase.concept.act_subgraph.act_observe_terminate_decide",
    Config=None,
    provides=("act::act.observe.terminate_decide",),
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
                "phase_concept_act_subgraph_act_observe_terminate_decide.checked",
                "phase_concept_act_subgraph_act_observe_terminate_decide.served",
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
    executor = ActObserveTerminateDecideExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActObserveTerminateDecideExecutor", "setup"]
