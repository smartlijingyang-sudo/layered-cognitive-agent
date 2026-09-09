"""Shared carry and step helpers for the decomposed think subgraph."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, cast

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import SupportsShortcut
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.gate.decision_classifier import DecisionClassifier
from lca.contracts.protocols.state.reducer import Reducer
from lca.contracts.protocols.think.cognition import Brain, DecisionGate, Reasoner, SkillRouter
from lca.infrastructure.session.emit.cognitive_emit import run_brain_think_with_spine_facts
from lca.loop.emit.cognitive.reasoner import run_reasoner_with_spine_facts
from lca.plugins.loop.phase._shared.capabilities import StandardPhaseCapabilities
from lca.plugins.loop.phase._shared.common import fallback_phase_result

CARRY_KEY = "think.subgraph.carry"
STAGE_KIND = "think_stage"


@dataclass(slots=True)
class ThinkSubgraphCarry:
    """Mutable working state passed between think subgraph nodes."""

    state: AgentState
    response: LLMResponse | None = None
    decision: Decision | None = None


@dataclass(frozen=True, slots=True)
class ThinkCollaborators:
    """Production think dependencies extracted from a profile-selected Brain."""

    reasoner: Reasoner
    classifier: DecisionClassifier
    skill_router: SkillRouter | None
    decision_gate: DecisionGate | None
    agent_gates: DecisionGate | None
    reducer: Reducer | None


def carry_from_context(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


def stage_result(carry: ThinkSubgraphCarry) -> PhaseResult:
    return PhaseResult(result_kind=STAGE_KIND, payload=carry)


def decision_result(decision: Decision) -> PhaseResult:
    return PhaseResult(result_kind="decision", payload=decision)


def collaborators_from_context(context: PhaseContext) -> ThinkCollaborators | None:
    brain = StandardPhaseCapabilities(context.capabilities).brain
    if brain is None:
        return None
    return collaborators_from_brain(brain)


def collaborators_from_brain(brain: Brain) -> ThinkCollaborators | None:
    reasoner = getattr(brain, "reasoner", None)
    classifier = getattr(brain, "classifier", None)
    if reasoner is None or classifier is None:
        return None
    decision_gate = getattr(brain, "_decision_gate", None)
    if decision_gate is None:
        decision_gate = getattr(brain, "decision_gate", None)
    return ThinkCollaborators(
        reasoner=cast("Reasoner", reasoner),
        classifier=cast("DecisionClassifier", classifier),
        skill_router=cast("SkillRouter | None", getattr(brain, "skill_router", None)),
        decision_gate=cast("DecisionGate | None", decision_gate),
        agent_gates=cast("DecisionGate | None", getattr(brain, "agent_gates", None)),
        reducer=cast("Reducer | None", getattr(brain, "reducer", None)),
    )


async def run_shortcut_step(context: PhaseContext, input: PhaseInput) -> PhaseResult:
    collaborators = collaborators_from_context(context)
    if collaborators is None:
        return fallback_phase_result(
            phase=SemanticPhase.THINK,
            result_kind="decision",
            input=input,
        )
    carry = carry_from_context(context)
    gate = collaborators.decision_gate
    if gate is not None and isinstance(gate, SupportsShortcut):
        shortcut = await gate.try_shortcut(carry.state)
        if shortcut is not None:
            return decision_result(shortcut)
    return stage_result(carry)


async def run_route_step(context: PhaseContext, input: PhaseInput) -> PhaseResult:
    collaborators = collaborators_from_context(context)
    carry = carry_from_context(context)
    if collaborators is None or collaborators.skill_router is None:
        return stage_result(carry)
    if collaborators.reducer is None:
        raise RuntimeError(
            "Think subgraph route step requires Reducer when SkillRouter is configured"
        )
    active_template = await collaborators.skill_router.route(carry.state)
    routed_state = collaborators.reducer.apply_skill_route(carry.state, active_template)
    return stage_result(replace(carry, state=routed_state))


async def run_reason_step(context: PhaseContext, input: PhaseInput) -> PhaseResult:
    collaborators = collaborators_from_context(context)
    carry = carry_from_context(context)
    if collaborators is None:
        return fallback_phase_result(
            phase=SemanticPhase.THINK,
            result_kind=STAGE_KIND,
            input=input,
        )
    response = await run_reasoner_with_spine_facts(collaborators.reasoner, carry.state)
    return stage_result(replace(carry, response=response))


async def run_classify_step(context: PhaseContext, input: PhaseInput) -> PhaseResult:
    collaborators = collaborators_from_context(context)
    carry = carry_from_context(context)
    if collaborators is None or carry.response is None:
        return fallback_phase_result(
            phase=SemanticPhase.THINK,
            result_kind=STAGE_KIND,
            input=input,
        )
    decision = collaborators.classifier.classify(carry.response)
    return stage_result(replace(carry, decision=decision))


async def run_gate_step(context: PhaseContext, input: PhaseInput) -> PhaseResult:
    collaborators = collaborators_from_context(context)
    carry = carry_from_context(context)
    if collaborators is None or carry.decision is None:
        return fallback_phase_result(
            phase=SemanticPhase.THINK,
            result_kind="decision",
            input=input,
        )
    decision = carry.decision
    if collaborators.decision_gate is not None:
        decision = await collaborators.decision_gate.enforce(carry.state, decision)
    if collaborators.agent_gates is not None:
        decision = await collaborators.agent_gates.enforce(carry.state, decision)
    return decision_result(decision)


async def run_pipeline_via_brain(context: PhaseContext, input: PhaseInput) -> PhaseResult:
    """Reference path used by parity tests and the standard executor."""

    brain = StandardPhaseCapabilities(context.capabilities).brain
    if brain is None:
        return fallback_phase_result(
            phase=SemanticPhase.THINK,
            result_kind="decision",
            input=input,
        )
    decision = await run_brain_think_with_spine_facts(brain, context.state)
    return decision_result(decision)


def step_plugin_spec(*, plugin_id: str, module: str) -> Any:
    from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
        CapabilityDeclaration,
        ContributionRole,
        EvidenceDeclaration,
        LifecycleDeclaration,
        OwnershipDeclaration,
        PhaseContribution,
        PluginConfiguration,
        PluginImplementation,
        PluginSpec,
        PluginSpecKind,
        VerificationDeclaration,
    )

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
            schema="lca.plugins.loop.phase._shared.common.StandardPhaseConfig"
        ),
        provides=(
            CapabilityDeclaration(
                key=plugin_id,
                cardinality="one",
                protocol="PhaseExecutor",
                scope="run",
            ),
        ),
        requires=(),
        effects=("none",),
        ownership=OwnershipDeclaration(
            reads=("state.view", "journal.cursor"),
            emits=("phase.think.result",),
            state_mutation="forbidden",
        ),
        lifecycle=LifecycleDeclaration(scopes=("run",), activation="true", disposal="required"),
        relations=(),
        evidence=EvidenceDeclaration(emits=("PhaseThinkCompleted",), replay="required"),
        verification=VerificationDeclaration(
            test_suite="tests/cognition/test_think_subgraph_parity.py",
            properties=("phase_result_contract", "no_state_mutation"),
        ),
        contributes=(
            PhaseContribution(
                phase=SemanticPhase.THINK,
                role=ContributionRole.FINALIZE,
                executor=plugin_id,
                output="phase.think.result",
                order=0,
            ),
        ),
    )


__all__ = [
    "CARRY_KEY",
    "STAGE_KIND",
    "ThinkCollaborators",
    "ThinkSubgraphCarry",
    "carry_from_context",
    "collaborators_from_brain",
    "collaborators_from_context",
    "decision_result",
    "run_classify_step",
    "run_gate_step",
    "run_pipeline_via_brain",
    "run_reason_step",
    "run_route_step",
    "run_shortcut_step",
    "stage_result",
    "step_plugin_spec",
]
