"""phase.think.gate — enforce Decision via DecisionGate.

think 子图节点 plugin:用 DecisionGate 收敛候选 Decision。
``requires=("decision_gate",)`` 通过 Cordis 校验,
运行时从 ``context.runtime.decision_gate`` 拿 capability 实例。

ADR-0218 §3.3:节点 plugin 由作者显式书写完整 ``@plugin(...)`` 装饰器,
工厂 ``setup(ctx)`` 同时做 Cordis ``ctx.provide`` 与
``FactoryRegistry.register``(think 子图专用的 NodeExecutor 解析)。
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
from lca.contracts.protocols.think.cognition import DecisionGate
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_SEMANTIC_NAME = "think.gate"
_REGION = "phase:think"


@dataclass(frozen=True, slots=True)
class ThinkGateExecutor:
    """think 节点:把 Decision 经 DecisionGate 收敛。"""

    semantic_name: str = _SEMANTIC_NAME

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
        state = runtime.state
        gate = runtime.decision_gate
        decision = input.port_values.get("decision")

        if decision is None:
            return NodeOutput(port_values={})

        if state is not None and isinstance(gate, DecisionGate):
            decision = await gate.enforce(state, decision)

        return NodeOutput(
            port_values={
                "enforced_decision": decision,
                "think_signal": "gated",
            },
        )


@plugin(
    id="phase.think.gate",
    Config=None,
    provides=("phase.think.gate",),
    requires=("decision_gate",),
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
                "phase_think_gate.checked",
                "phase_think_gate.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "decision_gate"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """双注册:Cordis provide + FactoryRegistry register。"""
    del config
    executor = ThinkGateExecutor()
    ctx.provide("phase.think.gate", executor)
    get_default_registry().register(
        executor,
        semantic_name=_SEMANTIC_NAME,
        region=_REGION,
    )


__all__ = ["ThinkGateExecutor", "setup"]
