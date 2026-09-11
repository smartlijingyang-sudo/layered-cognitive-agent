"""phase.concept.decision_enforce.gate_chain_run — typed gate chain runner.

concept.decision.enforce 图节点 1:typed ``Decision`` + ``AgentState``
→ enforced ``Decision``(ADR-0220 §3.3)。

节点职责:把 ``DecisionGate`` chain 跑一遍,产出一个可能被 rewrite 的
typed ``Decision``。gate 列表从 ``context.runtime.decision_gates`` 拿
(typed list,运行时由 ``ChainedDecisionGate`` 装配);空 chain → 直接
透传 Decision,等同 "no-op gate"。
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
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate
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
class GateChainRunExecutor:
    """concept.decision.enforce 节点 1:跑 gate chain,rewrite Decision。"""

    semantic_name: str = "gate.chain.run"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("decision", "state")
    declared_outputs: tuple[PortName, ...] = ("enforced_decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """gate.chain.run 入口。

        inputs 端口(yaml):decision (Decision), state (AgentState)
        outputs 端口(yaml):enforced_decision (Decision)
        """
        decision = input.port_values.get("decision")
        state = input.port_values.get("state")
        if not isinstance(decision, Decision):
            raise TypeError(
                f"gate.chain.run: 'decision' port must be a Decision, got {type(decision).__name__}"
            )
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "gate.chain.run: 'state' port must be an AgentState or None, "
                f"got {type(state).__name__}"
            )

        gates = _resolve_gates(context)
        enforced = await _run_chain(gates, state, decision)
        return NodeOutput(port_values={"enforced_decision": enforced})


def _resolve_gates(context: NodeContext) -> tuple[DecisionGate, ...]:
    """Resolve the DecisionGate chain from runtime context.

    Accepts either a single ``DecisionGate`` (typically the
    ``ChainedDecisionGate`` from ``lca.cognition.brain.decision_gates.chained``)
    or an iterable of gates; both shapes are common depending on how the
    parent profile wires the capability.
    """
    runtime = context.runtime
    raw = getattr(runtime, "decision_gates", None)
    if raw is None:
        raw = getattr(runtime, "decision_gate", None)
    if raw is None:
        return ()
    if isinstance(raw, DecisionGate):
        return (raw,)
    try:
        items = tuple(raw)
    except TypeError:
        return ()
    return tuple(g for g in items if isinstance(g, DecisionGate))


async def _run_chain(
    gates: tuple[DecisionGate, ...],
    state: AgentState | None,
    decision: Decision,
) -> Decision:
    """Apply the gate chain in order.

    No gates wired → return the candidate unchanged. ``state=None``
    (e.g. tests that don't build a full state) → skip the chain so the
    node still produces a typed Decision; downstream
    ``gate.chain.reject`` checks against the candidate's identity to
    decide whether to attach a rejection receipt.
    """
    if not gates or state is None:
        return decision
    current = decision
    for gate in gates:
        current = await gate.enforce(state, current)
    return current


@plugin(
    id="phase.concept.decision_enforce.gate_chain_run",
    Config=None,
    provides=("concept::gate.chain.run",),
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
                "phase_concept_decision_enforce_gate_chain_run.checked",
                "phase_concept_decision_enforce_gate_chain_run.served",
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
    executor = GateChainRunExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["GateChainRunExecutor", "setup"]
