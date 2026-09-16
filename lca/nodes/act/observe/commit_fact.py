"""phase.concept.act_subgraph.act_observe_commit_fact — typed observation-plane journal commit.

``concept.act_subgraph`` 内嵌节点:``EffectReceipt`` → ``EffectReceipt``
(透传)+ 调用 ``journal.commit_fact(RunFact(kind="effect.observed", ...))``
一次。

PR-3 Task 3.2.7a:从原 ``act.observe`` 节点剥离 ``RunFact commit`` 段,
让 ``act.observe`` 只承担 receipt 归一化,本节点专门承担 observation plane
落库职责(AGENTS.md §2.2 事实写入与数据归一化分离)。

journal capability 的取用方式与拆分前一致:仍从 kernel 注入的
``context.runtime`` 上取 ``journal``。因此本节点**没有**消除 act 节点读取
graph runtime 的边界问题,只是把它收敛到单一职责的一处;该边界与
``getattr(..., None)`` 的静默降级一并由 PR-5(ADR-0235)处理。

Deterministic + idempotent:同一 receipt 多次调用产生相同 ``fact_id``
且 ``commit_fact`` 被调用 N 次(节点本身不负责去重;去重由 journal
capability 实现负责)。
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
from lca.contracts.protocols.act.command.envelope import RunFact
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


def _resolve_plan_ref(metadata: dict[str, object]) -> str:
    value = metadata.get("plan_ref", "unknown")
    return value if isinstance(value, str) else "unknown"


def _resolve_node_ref(metadata: dict[str, object], fallback: str) -> str:
    value = metadata.get("node_id", fallback)
    return value if isinstance(value, str) else fallback


@dataclass(frozen=True, slots=True)
class ActObserveCommitFactExecutor:
    """``concept.act_subgraph`` 节点:EffectReceipt → EffectReceipt + journal commit。

    Reads the ``receipt`` port, constructs a typed ``RunFact(kind=
    "effect.observed", payload={...})`` and calls
    ``journal.commit_fact(fact, plan_ref=..., node_ref=...)`` once if the
    kernel has injected a ``journal`` capability on ``context.runtime``.
    The receipt is passed through unchanged on the ``receipt`` port.
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

        副作用:``context.runtime.journal`` typed capability 可用时,
        调 ``journal.commit_fact(RunFact(kind="effect.observed", ...), ...)``
        一次。journal capability 不可用 → passthrough(act 业务不依赖 journal)。
        """
        receipt = input.port_values.get("receipt")
        if not isinstance(receipt, EffectReceipt):
            raise TypeError(
                "act.observe.commit_fact: 'receipt' port must be an EffectReceipt "
                f"instance, got {type(receipt).__name__}"
            )

        runtime = context.runtime
        journal = getattr(runtime, "journal", None) if runtime is not None else None
        plan_ref = _resolve_plan_ref(context.metadata)
        node_ref = _resolve_node_ref(context.metadata, self.semantic_name)

        if journal is not None and hasattr(journal, "commit_fact"):
            fact = RunFact(
                fact_id=f"{plan_ref}:{node_ref}:{receipt.invocation_id}",
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
            journal.commit_fact(fact, plan_ref=plan_ref, node_ref=node_ref)

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
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = ActObserveCommitFactExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActObserveCommitFactExecutor", "setup"]
