"""phase.think.gate — enforce Decision via DecisionGate and optional agent gates.

ADR-0217 §3.3:本 plugin 实现 NodeExecutor 协议(think 子图专用),同时保留
@plugin(...) 装饰器注册(Cordis 容器兼容)。双注册互不替代。
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
from lca.contracts.plugins.think.step_plugin_spec import step_plugin_spec
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_1.factory_resolver import (
    get_default_registry,
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
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig

_SEMANTIC_NAME = "think.gate"
_REGION = "phase:think"

SPEC = step_plugin_spec(
    plugin_id="phase.think.gate",
    module="lca.plugins.think.gate.plugin",
    test_suite="tests/think/test_gate_phase_plugin.py",
)


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkGateExecutor:
    """think 节点:把 Decision 经 DecisionGate 收敛。"""

    semantic_name: str = _SEMANTIC_NAME

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        # 老 PhaseExecutor 路径(保留 carry 语义,兼容 tests + 老 caller)
        carry = _carry(context)
        if carry.decision is None:
            # 老行为:无 decision 时返回 result_kind="decision",payload=input.artifact
            return PhaseResult(result_kind="decision", payload=input.artifact)
        decision = carry.decision
        gate = context.capabilities.get("phase.think.gate")
        if isinstance(gate, DecisionGate):
            decision = await gate.enforce(carry.state, decision)
        agent_gates = context.capabilities.get("phase.think.agent_gates")
        if isinstance(agent_gates, DecisionGate):
            decision = await agent_gates.enforce(carry.state, decision)
        return PhaseResult(result_kind="decision", payload=decision)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml):decision, in_state
        outputs 端口(yaml):enforced_decision, think_signal
        """
        runtime = context.runtime
        state = runtime.get("state") if isinstance(runtime, dict) else None
        gate = runtime.get("decision_gate") if isinstance(runtime, dict) else None
        agent_gates = runtime.get("agent_gates") if isinstance(runtime, dict) else None
        decision = input.port_values.get("decision")

        if decision is None:
            return NodeOutput(port_values={})

        if state is not None and isinstance(gate, DecisionGate):
            decision = await gate.enforce(state, decision)
        if state is not None and isinstance(agent_gates, DecisionGate):
            decision = await agent_gates.enforce(state, decision)

        return NodeOutput(
            port_values={
                "enforced_decision": decision,
                "think_signal": "gated",
            },
        )


@plugin(
    id="phase.think.gate",
    Config=StandardPhaseConfig,
    provides=("phase.think.gate",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_gate_phase_plugin.py",
    spec=SPEC,
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
                "phase_think_gate.checked",
                "phase_think_gate.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    """双注册:cordis provide + FactoryRegistry register。"""
    del config
    executor = ThinkGateExecutor()
    ctx.provide("phase.think.gate", executor)
    get_default_registry().register(
        executor,
        semantic_name=_SEMANTIC_NAME,
        region=_REGION,
    )


def create_executor() -> ThinkGateExecutor:
    return ThinkGateExecutor()


__all__ = ["ThinkGateExecutor", "create_executor", "setup"]
