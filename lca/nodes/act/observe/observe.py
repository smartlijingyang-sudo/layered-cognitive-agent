"""phase.concept.act_subgraph.act_observe — typed effect observation node.

``concept.act_subgraph`` 内嵌节点:``EffectReceipt`` → ``EffectReceipt``
。

act 子图最后一个节点,在执行完成后观察回执并写入 journal 一条 ``effect.observed``
事实(若 ``journal`` capability 可用),让下游 reflect / remember 节点可以做
typed 推断。

PR-3.8.7: 本节点同时承担 ``act.result.normalize`` 的归一化语义(merge
target,见 spec §3.3)。归一化在 ``node_execute`` 内部完成,不改
``declared_inputs`` / ``declared_outputs``,typed-boundary port schema
对外不可见(AGENTS.md §3 C13)。不要把归一化拆成单独的 graph node。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

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
from lca.contracts.observability.observability.failure_reason_map import (
    resolve_error_reason,
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

# ADR-0197 ``guard.tool-result-spill`` 阈值(50_000 字节)。``output_ref`` 超过该
# 阈值视为 inline 负载溢出,emit stub receipt 并把 ``output_ref`` 改写为合成的
# spill URI,避免下游 typed 推断时把超大 inline 引用当成有效负载。
_MAX_OUTPUT_REF_BYTES = 50_000
_SPILL_URI_PREFIX = "spill://"


def _normalize_receipt(receipt: EffectReceipt) -> EffectReceipt:
    """``act.observe`` 内部归一化步骤(PR-3.8.7 fold from ``act.result.normalize``)。

    Idempotent + deterministic:同一 ``receipt`` 多次调用产生结构等价的
    ``EffectReceipt``(字段值相同,允许新实例)。无更新时返回同一实例,
    保证 ``tests/loop/test_act_observe_should_terminate.py`` 的 ``is``
    身份断言继续成立。

    归一化规则(plan §Task 1):
      1. 剥离不可序列化字段 — ``EffectReceipt`` 字段均为基础类型,no-op。
      2. bytes ≤ 50_000 → base64-string — receipt 无 inline 字节负载,no-op。
      3. bytes > 50_000 → spill 到 side artifact,``output_ref`` 改写为
         ``spill://<invocation_id>`` URI,emit stub receipt。
      4. ``failure_kind`` 已设置且 ``error_code`` 仍为空时,从 contracts
         closed-set map 推导 ``error_reason`` 并写入 ``error_code``
         (deterministic, no exception; PR-4 single-source)。已设置的
         ``error_code`` 不覆盖(body 已分类更具体)。
    """
    updates: dict[str, Any] = {}

    if (
        receipt.output_ref is not None
        and len(receipt.output_ref.encode("utf-8")) > _MAX_OUTPUT_REF_BYTES
    ):
        updates["output_ref"] = f"{_SPILL_URI_PREFIX}{receipt.invocation_id}"

    if receipt.failure_kind is not None and receipt.error_code is None:
        reason = resolve_error_reason(receipt.failure_kind)
        if reason is not None:
            updates["error_code"] = reason

    if not updates:
        return receipt
    return dataclasses.replace(receipt, **updates)


@dataclass(frozen=True, slots=True)
class ActObserveExecutor:
    """``concept.act_subgraph`` 节点:EffectReceipt → EffectReceipt(passthrough)。"""

    semantic_name: str = "act.observe"
    region: str = "act"
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

        Deterministic-failure shortcut (plan
        ``docs/plans/2026-09-14-stop-decision-retirement.md``, PR-3):
        when the receipt's ``extra[FAILURE_KIND] == EXECUTION``,
        ``act.observe`` emits a ``should_terminate=true`` payload on
        the result node, and the outer driver routes the next edge
        to ``terminal.commit`` instead of looping back to think.
        Body's deterministic-failure signal (failure_kind=execution)
        is the single source of truth for "the model cannot make
        progress on this path".
        """
        receipt = input.port_values.get("receipt")
        if not isinstance(receipt, EffectReceipt):
            raise TypeError(
                "act.observe: 'receipt' port must be an EffectReceipt "
                f"instance, got {type(receipt).__name__}"
            )

        # PR-3.8.7: normalize before emit (folded from ``act.result.normalize``).
        # The normalize step is idempotent + deterministic; the typed-boundary port
        # schema (``declared_inputs`` / ``declared_outputs``) is unchanged.
        normalized = _normalize_receipt(receipt)

        journal = getattr(context.runtime, "journal", None)
        plan_ref = context.metadata.get("plan_ref", "unknown")
        node_id = context.metadata.get("node_id", "act.observe")
        if journal is not None and hasattr(journal, "commit_fact"):
            from lca.contracts.protocols.act.command.envelope import RunFact

            fact = RunFact(
                fact_id=f"{plan_ref}:{node_id}:{normalized.invocation_id}",
                plan_ref=plan_ref,
                kind="effect.observed",
                payload={
                    "invocation_id": normalized.invocation_id,
                    "outcome": normalized.outcome.value,
                    "provider": normalized.provider,
                    "idempotency_key": normalized.idempotency_key,
                    "error_code": normalized.error_code,
                },
            )
            journal.commit_fact(fact, plan_ref=plan_ref, node_ref=node_id)

        should_terminate = False
        if normalized.failure_kind == FAILURE_KIND_EXECUTION or (
            normalized.failure_kind is None and normalized.outcome.value == "failed"
        ):
            should_terminate = True

        return NodeOutput(
            port_values={
                "receipt": normalized,
                "should_terminate": should_terminate,
            }
        )


@plugin(
    id="phase.concept.act_subgraph.act_observe",
    Config=None,
    provides=("act::act.observe",),
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
