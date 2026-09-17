"""phase.concept.act_subgraph.act_observe_terminate_decide — typed should_terminate decision.

``concept.act_subgraph`` 内嵌节点:``EffectReceipt`` →
``EffectReceipt`` + ``should_terminate``(纯路由决策)。

PR-3 split:本节点从原 ``act.observe`` 中剥离 ``should_terminate`` 决策,
使 ``act.observe`` 节点只承担 receipt 归一化 + RunFact commit(由同级
``act.observe.commit_fact`` 节点承担),节点职责符合 AGENTS.md §2.2
「事实源 ≠ 决策」分类。

决策规则(确定性 + 幂等):

    should_terminate = receipt.failure_kind is None and receipt.outcome.value == "failed"

只有*未分类*的失败才终止 run —— 那是 host 侧根本没能把 effect 派出去
(``concept.effect.execute`` 捕获 gateway 异常时产出的 receipt 无
``failure_kind``)。带分类标签的失败是工具对*自己标的物*的报告,必须回到
模型手里让它换方案(docs/specs/tool-failure-recovery.md §3/§6.1/§7)。
一个 turn fork 出的 N 个工具调用只产出一张 receipt,其标签由
``fold_failure_kinds`` 从失败分量折出(``ToolBatchExecutor``),所以「批里
有工具失败」不会被读成「没有工具报告过结果」。
卡死的循环由 ``think.budget.gate`` 兜住(每轮 think 都跑,``max_steps=50`` /
300s 墙钟);ADR-0225 已删除 per-node ``max_visits``,ADR-0230 当初为省掉
``max_visits=8`` 空转而在这一节点加的 deterministic-failure 短路已无前提。
``ToolLoopBreakerGate`` / ``ProgressLoopDetector`` 本应是更紧的界,但两者都读
``control_turns``,而生产里没有任何一处构造 ``RunDelta``,通往 ``apply_turn``
的链从不执行,所以它们每次都读到 0 条 turn —— 详见 ADR-0230 Amendment。

无副作用:不调 journal,不调 Body / Registry / SafeExecutor,不构造 envelope。
typed-port 边界:输入 ``receipt``、输出 ``receipt`` + ``should_terminate``。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
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

        决策规则:仅当 receipt 是*未分类*失败(``failure_kind is None`` 且
        ``outcome == failed``,即 host 侧派发失败)时 emit
        ``should_terminate=True``;任何带分类标签的失败(execution /
        transient / validation / tool_wire)都 emit ``False``,让失败
        Observation 回到模型。
        """
        del context  # unused: pure function of input port value
        receipt = input.port_values.get("receipt")
        if not isinstance(receipt, EffectReceipt):
            raise TypeError(
                "act.observe.terminate_decide: 'receipt' port must be an "
                f"EffectReceipt instance, got {type(receipt).__name__}"
            )

        should_terminate = receipt.failure_kind is None and receipt.outcome.value == "failed"

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
