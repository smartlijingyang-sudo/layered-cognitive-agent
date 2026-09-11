"""phase.concept.stop_should_check.stop_should_decide — typed stop policy.

concept.stop.should_check 图节点 1:typed ``AgentState`` + ``Decision | None``
+ ``Observation | None`` + ``Reflection | None`` → ``StopDecision`` typed
(ADR-0220 §3.3 + §4.2)。

节点职责:调 ``StopPolicy.decide(state, decision, observation, reflection)``,
 产出 typed ``StopDecision``。``StopPolicy`` capability 从 ``runtime.stop_policy``
读;缺失 capability → RuntimeError(fail-loud)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    Reflection,
)
from lca.contracts.models.core.policy.stop import StopDecision
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.runtime.runtime.runtime import StopPolicy
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class StopShouldDecideExecutor:
    """concept.stop.should_check 节点 1:state + decision + obs + reflection → StopDecision。"""

    semantic_name: str = "stop.should.decide"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("state", "decision", "observation", "reflection")
    declared_outputs: tuple[PortName, ...] = ("stop_decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """stop.should.decide 入口。

        inputs 端口(yaml):state (AgentState), decision (Decision | None),
        observation (Observation | None), reflection (Reflection | None)
        outputs 端口(yaml):stop_decision (StopDecision)
        """
        runtime = context.runtime
        state = input.port_values.get("state") or runtime.state
        decision = input.port_values.get("decision")
        observation = input.port_values.get("observation")
        reflection = input.port_values.get("reflection")

        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "stop.should.decide: 'state' port must be an AgentState "
                f"instance or None, got {type(state).__name__}"
            )
        if decision is not None and not isinstance(decision, Decision):
            raise TypeError(
                "stop.should.decide: 'decision' port must be a Decision or "
                f"None, got {type(decision).__name__}"
            )
        if observation is not None and not isinstance(observation, Observation):
            raise TypeError(
                "stop.should.decide: 'observation' port must be an Observation "
                f"or None, got {type(observation).__name__}"
            )
        if reflection is not None and not isinstance(reflection, Reflection):
            raise TypeError(
                "stop.should.decide: 'reflection' port must be a Reflection "
                f"or None, got {type(reflection).__name__}"
            )

        policy = _resolve_stop_policy(runtime)
        stop_decision = policy.decide(state, decision, observation, reflection)
        if not isinstance(stop_decision, StopDecision):
            raise TypeError(
                "stop.should.decide: StopPolicy.decide must return a "
                f"StopDecision instance, got {type(stop_decision).__name__}"
            )
        return NodeOutput(port_values={"stop_decision": stop_decision})


def _resolve_stop_policy(runtime: Any) -> StopPolicy:
    """Resolve the StopPolicy capability from runtime context."""
    policy = getattr(runtime, "stop_policy", None)
    if not isinstance(policy, StopPolicy):
        raise RuntimeError(
            "stop.should.decide: 'stop_policy' capability missing from runtime "
            "scope — wire a StopPolicy provider before concept.stop.should_check runs."
        )
    return policy


@plugin(
    id="phase.concept.stop_should_check.stop_should_decide",
    Config=None,
    provides=("concept::stop.should.decide",),
    requires=("stop_policy",),
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
                "phase_concept_stop_should_check_stop_should_decide.checked",
                "phase_concept_stop_should_check_stop_should_decide.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "stop_policy"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = StopShouldDecideExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["StopShouldDecideExecutor", "setup"]
