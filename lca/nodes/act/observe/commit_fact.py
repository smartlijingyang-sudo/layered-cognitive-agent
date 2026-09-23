"""phase.concept.act_subgraph.act_observe_commit_fact — receipt passthrough.

``concept.act_subgraph`` 内嵌节点:``EffectReceipt`` → ``EffectReceipt``
(纯透传)。

PR-3 close-out: 原本的 ``commit_fact`` 节点同时承担 receipt 归一化与
``journal.commit_fact(RunFact(kind="effect.observed", ...))`` 副作用
(observation plane 落库),后者被 PR-5 commit 进一步收紧为 typed
``JournalCapability.commit_fact`` 注入。两次拆解都把 commit 留在 act 业务
节点内,与 AGENTS.md §2.2 (事实/状态/决策/许可/回执/投影 单一职责) 冲突
——``JournalCapability`` 是 PR-3 自造的旁路机制,绕开了 ADR-0192 规定的
``FactCommitter`` 走 ``Session.append`` 单轨。

Redesign-from-first-principles 收尾 (LCA AGENTS.md §1.5 #2 直击本质):

- 节点只做 receipt passthrough。RunFact 构造 + 落库由上游 ``reducer.fold``
  走 ``FactCommitter`` / ``Session.append`` 完成,严格单一职责。
- typed-port wiring 边界 (ADR-0195 §1.4 C13) 保留:``receipt → receipt``
  不引入 journal capability、Context.runtime peek、或任何旁路。
- 删除 PR-3 引入的 ``JournalCapability`` Protocol 与 ``JournalBackendAdapter``
  shim;两者在仓库内不再有消费者。
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
class ActObserveCommitFactExecutor:
    """``concept.act_subgraph`` 节点:EffectReceipt → EffectReceipt passthrough。

    PR-3 close-out: receipt 透传归一化后,RunFact 落库由 reducer.fold 走
    ``FactCommitter`` 单轨(ADR-0192)完成,本节点零副作用、不读取
    ``context.runtime``、不构造 journal/journal_capability dependency。
    """

    semantic_name: str = "act.observe.commit_fact"
    region: str = "act"
    declared_inputs: tuple[PortName, ...] = ("receipt",)
    declared_outputs: tuple[PortName, ...] = ("receipt",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.observe.commit_fact 入口。

        inputs 端口(yaml): receipt (EffectReceipt)
        outputs 端口(yaml): receipt (EffectReceipt, passthrough)

        无副作用。Receipt 类型不匹配 → ``TypeError``(typed-port 边界
        fail-loud,AGENTS.md §3 C13)。
        """
        del context  # unused: pure function of input ports
        receipt = input.port_values.get("receipt")
        if not isinstance(receipt, EffectReceipt):
            raise TypeError(
                "act.observe.commit_fact: 'receipt' port must be an EffectReceipt "
                f"instance, got {type(receipt).__name__}"
            )
        return NodeOutput(port_values={"receipt": receipt})


@plugin(
    id="phase.concept.act_subgraph.act_observe_commit_fact",
    Config=None,
    provides=("act::act.observe.commit_fact",),
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
                "phase_concept_act_subgraph_act_observe_commit_fact.checked",
                "phase_concept_act_subgraph_act_observe_commit_fact.served",
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
    """Composite-key 注册:``{region}::{semantic_name}``。

    PR-3 close-out: 不再 require ``journal_capability`` /
    ``journal_backends`` —— RunFact commit 走 reducer 单轨(ADR-0192)。
    """
    del config
    executor = ActObserveCommitFactExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActObserveCommitFactExecutor", "setup"]
