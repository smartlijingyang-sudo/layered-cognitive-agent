"""标准 PhaseExecutor 插件的共享声明与无副作用默认实现。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols.command_envelope import CapabilityGrant, RunDelta, mint_envelope
from lca.contracts.protocols.declarative_phase_graph import (
    CapabilityDeclaration,
    ContributionRole,
    EvidenceDeclaration,
    LifecycleDeclaration,
    OwnershipDeclaration,
    PhaseContribution,
    PhaseExecutor,
    PhaseInput,
    PhaseResult,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    SemanticPhase,
    VerificationDeclaration,
)


class StandardPhaseConfig(BaseModel):
    """标准阶段执行器的显式空配置 schema。"""


@dataclass(frozen=True, slots=True)
class StandardPhaseExecutor(PhaseExecutor):
    """安全的最小 PhaseExecutor。

    它用于 Null / smoke Profile：不读取 live Context、不产生世界效果，并返回可由
    通用解释器推进的标准 PhaseResult。实际认知实现应通过同一 capability 替换它。
    """

    phase: SemanticPhase

    async def execute(self, context: Any, input: PhaseInput) -> PhaseResult:
        """通过 ``PhaseContext`` 提供的受限 facade 执行一个声明的阶段。

        该实现从不接触 Cordis Context，也不会原地写入 State；对既有组件产生的
        状态变化一律编码为 RunDelta，交由 Reducer adapter 折叠。
        """
        capabilities = context.capabilities
        if self.phase is SemanticPhase.PERCEIVE:
            hub = _capability(capabilities, "perceive_hub")
            if hub is None:
                return _fallback(self.phase, input)
            manifest = await hub.perceive(context.state)
            return PhaseResult(
                result_kind="context",
                payload=manifest,
                deltas=(
                    RunDelta(
                        plan_ref=context.plan_ref,
                        metadata={
                            "operation": "step",
                            "step": getattr(context.state, "step", -1) + 1,
                        },
                    ),
                    RunDelta(
                        plan_ref=context.plan_ref,
                        metadata={"operation": "perception", "manifest": manifest},
                    ),
                ),
            )
        if self.phase is SemanticPhase.THINK:
            brain = _capability(capabilities, "brain")
            if brain is None:
                return _fallback(self.phase, input)
            decision = await brain.think(context.state)
            return PhaseResult(result_kind="decision", payload=decision)
        if self.phase is SemanticPhase.ACT:
            resume_input = _resume_input(context.state)
            approval_request = context.artifacts.get("approval_request")
            if resume_input is not None and approval_request is not None:
                return PhaseResult(
                    result_kind="observation",
                    payload=Observation(
                        observation_id=f"{context.plan_ref}:{context.node_ref}:human-input",
                        success=True,
                        payload=resume_input,
                        extra={
                            "source": "human_input",
                            "approval_request": approval_request,
                        },
                    ),
                )
            body = _capability(capabilities, "body")
            decision = context.artifacts.get("think")
            if body is None or decision is None:
                return _fallback(self.phase, input)
            envelope = mint_envelope(
                plan_ref=context.plan_ref,
                scope_ref=context.node_ref,
                decision=decision,
                provider="effect.body",
                grant=CapabilityGrant(capability="body.act", scope="run", effect_class="tools"),
                idempotency_key=f"{context.plan_ref}:{context.node_ref}:{decision.decision_id}",
                metadata={
                    "effect_class": "tools",
                    "operation": "body.act",
                    "state": context.state,
                    "decision": decision,
                },
            )
            return PhaseResult(result_kind="observation", command_envelope=envelope)
        if self.phase is SemanticPhase.REFLECT:
            brain = _capability(capabilities, "brain")
            observation = context.artifacts.get("act")
            if brain is None or observation is None:
                return _fallback(self.phase, input)
            reflection = await brain.reflect(context.state, observation)
            return PhaseResult(result_kind="reflection", payload=reflection)
        if self.phase is SemanticPhase.REMEMBER:
            memory = _capability(capabilities, "memory")
            decision = context.artifacts.get("think")
            observation = context.artifacts.get("act")
            reflection = context.artifacts.get("reflect")
            if memory is None or decision is None or observation is None or reflection is None:
                return _fallback(self.phase, input)
            envelope = mint_envelope(
                plan_ref=context.plan_ref,
                scope_ref=context.node_ref,
                decision=decision,
                provider="effect.memory",
                grant=CapabilityGrant(
                    capability="memory.update", scope="run", effect_class="memory"
                ),
                idempotency_key=f"{context.plan_ref}:{context.node_ref}:{decision.decision_id}",
                metadata={
                    "effect_class": "memory",
                    "operation": "memory.update",
                    "state": context.state,
                    "observation": observation,
                    "reflection": reflection,
                },
            )
            return PhaseResult(
                result_kind="write_set",
                payload={"admitted": True},
                command_envelope=envelope,
                deltas=(
                    RunDelta(
                        plan_ref=context.plan_ref,
                        metadata={
                            "operation": "turn",
                            "decision": decision,
                            "observation": observation,
                            "reflection": reflection,
                        },
                    ),
                    RunDelta(plan_ref=context.plan_ref, metadata={"operation": "memory"}),
                ),
            )
        stop_rule = _capability(capabilities, "stop_rule")
        if stop_rule is None:
            return _fallback(self.phase, input)
        stop = stop_rule.decide(
            context.state,
            context.artifacts.get("think"),
            context.artifacts.get("act"),
            context.artifacts.get("reflect"),
        )
        return PhaseResult(
            result_kind="stop_decision",
            payload=stop,
            deltas=(
                RunDelta(plan_ref=context.plan_ref, metadata={"operation": "stop", "stop": stop}),
            ),
        )


def _resume_input(state: Any) -> Any | None:
    working_memory = getattr(state, "working_memory", None)
    if isinstance(working_memory, dict):
        return working_memory.get("resume_input")
    return None


def _capability(capabilities: Any, name: str) -> Any:
    if isinstance(capabilities, dict):
        return capabilities.get(name)
    return getattr(capabilities, name, None)


def _fallback(phase: SemanticPhase, input: PhaseInput) -> PhaseResult:
    kinds = {
        SemanticPhase.PERCEIVE: "context",
        SemanticPhase.THINK: "decision",
        SemanticPhase.ACT: "observation",
        SemanticPhase.REFLECT: "reflection",
        SemanticPhase.REMEMBER: "write_set",
        SemanticPhase.STOP: "stop_decision",
    }
    payload: Any = {"phase": phase.value, "input": input.artifact}
    if phase is SemanticPhase.STOP:
        payload = {"should_stop": True, "phase": phase.value}
    return PhaseResult(result_kind=kinds[phase], payload=payload)


def standard_phase_spec(
    *,
    plugin_id: str,
    phase: SemanticPhase,
    module: str,
    effects: tuple[str, ...] = ("none",),
) -> PluginSpec:
    capability = f"phase.{phase.value}.standard"
    return PluginSpec(
        api_version="lca/plugin-spec/v1",
        id=plugin_id,
        revision="1.0.0",
        kind=PluginSpecKind.PHASE_EXECUTOR,
        layer="L2",
        functional_group="cognitive-phase",
        implementation=PluginImplementation(
            module=module, setup="setup", factory="create_executor"
        ),
        configuration=PluginConfiguration(
            schema="lca.plugins.phase_executors.common.StandardPhaseConfig"
        ),
        provides=(
            CapabilityDeclaration(
                key=capability,
                cardinality="one",
                protocol="PhaseExecutor",
                scope="run",
            ),
        ),
        requires=(),
        effects=effects,
        ownership=OwnershipDeclaration(
            reads=("state.view", "journal.cursor"),
            emits=(f"phase.{phase.value}.result",),
            state_mutation="forbidden",
        ),
        lifecycle=LifecycleDeclaration(scopes=("run",), activation="true", disposal="required"),
        relations=(),
        evidence=EvidenceDeclaration(
            emits=(f"Phase{phase.value.title()}Completed",), replay="required"
        ),
        verification=VerificationDeclaration(
            test_suite="tests/declarative/test_phase_graph.py",
            properties=("phase_result_contract", "no_state_mutation"),
        ),
        contributes=(
            PhaseContribution(
                phase=phase,
                role=ContributionRole.FINALIZE,
                executor=capability,
                output=f"phase.{phase.value}.result",
                order=0,
            ),
        ),
    )


__all__ = ["StandardPhaseConfig", "StandardPhaseExecutor", "standard_phase_spec"]
