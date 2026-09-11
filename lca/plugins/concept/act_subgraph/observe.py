"""phase.concept.act_subgraph.act_observe — typed effect observation node.

``concept.act_subgraph`` 内嵌节点:``EffectReceipt`` → ``EffectReceipt``
。

act 子图最后一个节点,在执行完成后观察回执并写入 journal 一条 ``effect.observed``
事实(若 ``journal`` capability 可用),让下游 reflect / remember 节点可以做
typed 推断。
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
class ActObserveExecutor:
    """``concept.act_subgraph`` 节点:EffectReceipt → EffectReceipt(passthrough)。"""

    semantic_name: str = "act.observe"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("receipt",)
    declared_outputs: tuple[PortName, ...] = ("receipt",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.observe 入口。

        inputs 端口(yaml): receipt (EffectReceipt)
        outputs 端口(yaml): receipt (EffectReceipt)

        记录一条 ``effect.observed`` RunFact 到 journal(若 runtime 暴露
        ``journal`` capability),让 reflect/remember 节点可以基于它做
        typed 推断。
        """
        receipt = input.port_values.get("receipt")
        if not isinstance(receipt, EffectReceipt):
            raise TypeError(
                "act.observe: 'receipt' port must be an EffectReceipt "
                f"instance, got {type(receipt).__name__}"
            )

        journal = getattr(context.runtime, "journal", None)
        plan_ref = context.metadata.get("plan_ref", "unknown")
        node_id = context.metadata.get("node_id", "act.observe")
        if journal is not None and hasattr(journal, "commit_fact"):
            from lca.contracts.protocols.act.command.envelope import RunFact

            fact = RunFact(
                fact_id=f"{plan_ref}:{node_id}:{receipt.invocation_id}",
                plan_ref=plan_ref,
                kind="effect.observed",
                payload={
                    "invocation_id": receipt.invocation_id,
                    "outcome": receipt.outcome.value,
                    "provider": receipt.provider,
                    "idempotency_key": receipt.idempotency_key,
                    "error_code": receipt.error_code,
                },
            )
            journal.commit_fact(fact, plan_ref=plan_ref, node_ref=node_id)

        return NodeOutput(port_values={"receipt": receipt})


@plugin(
    id="phase.concept.act_subgraph.act_observe",
    Config=None,
    provides=("concept::act.observe",),
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
                "phase_concept_act_subgraph_act_observe.checked",
                "phase_concept_act_subgraph_act_observe.served",
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
    executor = ActObserveExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActObserveExecutor", "setup"]
