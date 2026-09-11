"""phase.concept.decision_enforce.gate_chain_reject — typed rejection stamping.

concept.decision.enforce 图节点 2:candidate ``Decision`` + enforced
``Decision`` → final typed ``Decision``(ADR-0220 §3.3 + §4.2)。

节点职责:对比 candidate / enforced 两个 ``Decision``;enforced 与 candidate
不同 → 该决策被 gate chain rewrite / reject,落一个 ``Decision.degraded_from``
+ 最终 typed boundary。相同 → 直接透传 candidate,不打 reject 标签。

设计上保持图拓扑纯 typed 变换:enforced Decision 已经是 typed boundary
output,本节点只追加 ``degraded_from`` 标签,语义最小化。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

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
from lca.contracts.models.core.execution.decision import Decision
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
class GateChainRejectExecutor:
    """concept.decision.enforce 节点 2:candidate + enforced → stamped Decision。"""

    semantic_name: str = "gate.chain.reject"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("candidate", "enforced_decision")
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """gate.chain.reject 入口。

        inputs 端口(yaml):candidate (Decision), enforced_decision (Decision)
        outputs 端口(yaml):decision (Decision,可能被 stamped)
        """
        del context
        candidate = input.port_values.get("candidate")
        enforced = input.port_values.get("enforced_decision")
        if not isinstance(candidate, Decision):
            raise TypeError(
                "gate.chain.reject: 'candidate' port must be a Decision, "
                f"got {type(candidate).__name__}"
            )
        if not isinstance(enforced, Decision):
            raise TypeError(
                "gate.chain.reject: 'enforced_decision' port must be a Decision, "
                f"got {type(enforced).__name__}"
            )

        stamped = _stamp(candidate, enforced)
        return NodeOutput(port_values={"decision": stamped})


def _stamp(candidate: Decision, enforced: Decision) -> Decision:
    """Add ``degraded_from`` provenance when the gate rewrote the decision.

    When enforced.action_type matches candidate.action_type and the
    decision_id is the same (no rewrite happened), pass through. Otherwise
    mark the enforced Decision as a rewrite of the candidate's original
    action_type — this is the rejection provenance boundary.
    """
    if (
        enforced.action_type == candidate.action_type
        and enforced.decision_id == candidate.decision_id
        and enforced.degraded_from == candidate.degraded_from
    ):
        return enforced

    if enforced.degraded_from is not None:
        return enforced
    return replace(enforced, degraded_from=candidate.action_type)


@plugin(
    id="phase.concept.decision_enforce.gate_chain_reject",
    Config=None,
    provides=("concept::gate.chain.reject",),
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
                "phase_concept_decision_enforce_gate_chain_reject.checked",
                "phase_concept_decision_enforce_gate_chain_reject.served",
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
    executor = GateChainRejectExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["GateChainRejectExecutor", "_stamp", "setup"]
