"""phase.concept.reflection_critique.reflect_critique_run — typed Critic run.

concept.reflection.critique 图节点 2:typed ``Observation`` + ``AgentState``
→ ``Reflection`` typed boundary (ADR-0220 §3.3 + §4.2)。

节点职责:调 ``Critic.critique(state, observation)``, 产出 typed
``Reflection``。``Critic`` capability 从 ``runtime.critic`` 读;缺失
capability → RuntimeError(fail-loud),不允许静默回退到 NullCritic
(NullCritic 的语义是"显式配置";失败应被显式表达)。
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
from lca.contracts.models.core.execution.decision import Observation, Reflection
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
from lca.contracts.protocols.think.cognition import Critic
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ReflectCritiqueRunExecutor:
    """concept.reflection.critique 节点 2:Observation + state → Reflection。"""

    semantic_name: str = "reflect.critique.run"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("observation", "state")
    declared_outputs: tuple[PortName, ...] = ("reflection",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """reflect.critique.run 入口。

        inputs 端口(yaml):observation (Observation), state (AgentState)
        outputs 端口(yaml):reflection (Reflection)
        """
        runtime = context.runtime
        observation = input.port_values.get("observation")
        state = input.port_values.get("state") or runtime.state

        if not isinstance(observation, Observation):
            raise TypeError(
                "reflect.critique.run: 'observation' port must be an "
                f"Observation instance, got {type(observation).__name__}"
            )
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "reflect.critique.run: 'state' port must be an AgentState "
                f"instance or None, got {type(state).__name__}"
            )

        critic = _resolve_critic(runtime)
        reflection = await critic.critique(state, observation)
        if not isinstance(reflection, Reflection):
            raise TypeError(
                "reflect.critique.run: Critic.critique must return a "
                f"Reflection instance, got {type(reflection).__name__}"
            )
        return NodeOutput(port_values={"reflection": reflection})


def _resolve_critic(runtime: Any) -> Critic:
    """Resolve the Critic capability from runtime context."""
    critic = getattr(runtime, "critic", None)
    if not isinstance(critic, Critic):
        raise RuntimeError(
            "reflect.critique.run: 'critic' capability missing from runtime "
            "scope — wire a Critic provider (NullCritic / SimpleCritic / "
            "LcaReflectCriticProvider) before concept.reflection.critique runs."
        )
    return critic


@plugin(
    id="phase.concept.reflection_critique.reflect_critique_run",
    Config=None,
    provides=("concept::reflect.critique.run",),
    requires=("critic",),
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
                "phase_concept_reflection_critique_reflect_critique_run.checked",
                "phase_concept_reflection_critique_reflect_critique_run.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "critic"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = ReflectCritiqueRunExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ReflectCritiqueRunExecutor", "setup"]
