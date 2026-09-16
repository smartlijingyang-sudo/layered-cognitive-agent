"""phase.concept.act_subgraph.act_observe_normalize — typed receipt normalization node.

``concept.act_subgraph`` 内嵌节点:``EffectReceipt`` → ``EffectReceipt``
(归一化后透传)。

PR-3 split:本节点从原 ``act.observe`` 剥离 ``should_terminate`` 决策 +
``RunFact commit`` 两类职责,语义收紧为「receipt 归一化」(schema /
spill / coerce / error_reason)。决策由同级 ``act.observe.terminate_decide``
节点承担;observation plane 落库由同级 ``act.observe.commit_fact`` 节点承
担;两者通过 typed-port 边界串联,act 业务不再混 3 职责。

归一化规则(PR-3.8.7 fold from ``act.result.normalize``,Idempotent +
deterministic):

  1. 剥离不可序列化字段 — ``EffectReceipt`` 字段均为基础类型,no-op。
  2. bytes ≤ 50_000 → base64-string — receipt 无 inline 字节负载,no-op。
  3. bytes > 50_000 → spill 到 side artifact,``output_ref`` 改写为
     ``spill://<invocation_id>`` URI,emit stub receipt。
  4. ``failure_kind`` 已设置且 ``error_code`` 仍为空时,从 closed-set map
     推导 ``error_reason`` 并写入 ``error_code``(deterministic,no exception)。
     已设置的 ``error_code`` 不覆盖(body 已分类更具体)。

typed-boundary port schema(AGENTS.md §3 C13):``declared_inputs`` /
``declared_outputs`` 都是 ``("receipt",)``,归一化对调用者不可见。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TOOL_WIRE,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
)
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

# ADR-0197 ``guard.tool-result-spill`` 阈值(50_000 字节)。``output_ref`` 超过该
# 阈值视为 inline 负载溢出,emit stub receipt 并把 ``output_ref`` 改写为合成的
# spill URI,避免下游 typed 推断时把超大 inline 引用当成有效负载。
_MAX_OUTPUT_REF_BYTES = 50_000
_SPILL_URI_PREFIX = "spill://"

# Closed-set ``failure_kind`` → ``error_reason`` map(PR-3.8.7 merge from
# ``act.result.normalize``):同一 ``failure_kind`` 多次调用得到同一
# ``error_reason``(deterministic、idempotent)。未知 ``failure_kind`` 不抛异常、
# 不修改 ``error_code``(plan §Task 1 第 5 条)。PR-3 不删:PR-4 will 迁到
# ``lca/contracts/observability/observability/failure_reason_map.py``。
_FAILURE_KIND_TO_ERROR_REASON: dict[str, str] = {
    FAILURE_KIND_EXECUTION: FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT: FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION: FAILURE_KIND_VALIDATION,
    FAILURE_KIND_TOOL_WIRE: FAILURE_KIND_TOOL_WIRE,
}


def _normalize_receipt(receipt: EffectReceipt) -> EffectReceipt:
    """``act.observe.normalize`` 内部归一化步骤。

    Idempotent + deterministic:同一 ``receipt`` 多次调用产生结构等价的
    ``EffectReceipt``(字段值相同,允许新实例)。无更新时返回同一实例,
    保证归一化单测的 ``is`` 身份断言继续成立。

    归一化规则:见模块 docstring 第 1-4 条。
    """
    updates: dict[str, Any] = {}

    if (
        receipt.output_ref is not None
        and len(receipt.output_ref.encode("utf-8")) > _MAX_OUTPUT_REF_BYTES
    ):
        updates["output_ref"] = f"{_SPILL_URI_PREFIX}{receipt.invocation_id}"

    if receipt.failure_kind is not None and receipt.error_code is None:
        reason = _FAILURE_KIND_TO_ERROR_REASON.get(receipt.failure_kind)
        if reason is not None:
            updates["error_code"] = reason

    if not updates:
        return receipt
    return dataclasses.replace(receipt, **updates)


@dataclass(frozen=True, slots=True)
class ActObserveExecutor:
    """``concept.act_subgraph`` 节点:EffectReceipt → EffectReceipt(passthrough after normalize)。

    PR-3:语义改为 normalize only。``should_terminate`` 决策由同级
    ``act.observe.terminate_decide`` 节点产出;observation plane 落库由同级
    ``act.observe.commit_fact`` 节点完成。本节点无副作用:不读 context.runtime,
    不调 journal,不写 journal,只做 receipt 字段归一化后透传。
    """

    semantic_name: str = "act.observe.normalize"
    region: str = "act"
    declared_inputs: tuple[PortName, ...] = ("receipt",)
    declared_outputs: tuple[PortName, ...] = ("receipt",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.observe.normalize 入口。

        inputs 端口(yaml): receipt (EffectReceipt)
        outputs 端口(yaml): receipt (EffectReceipt, normalized passthrough)

        无副作用:归一化是纯函数。无 journal writes、无 should_terminate 计算,
        无 ``context.runtime`` 读取(observation-plane 落库由下游
        ``act.observe.commit_fact`` 节点通过 typed-port capability 注入)。
        """
        del context  # unused: pure function of input port value
        receipt = input.port_values.get("receipt")
        if not isinstance(receipt, EffectReceipt):
            raise TypeError(
                "act.observe.normalize: 'receipt' port must be an EffectReceipt "
                f"instance, got {type(receipt).__name__}"
            )

        normalized = _normalize_receipt(receipt)
        return NodeOutput(port_values={"receipt": normalized})


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
