"""Parity between ``phase.think.standard`` and ``phase.think.subgraph_host``."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lca.cognition.brain.pipeline.cognitive_pipeline import StandardCognitiveThinkPipeline
from lca.cognition.brain.pipeline.modular_brain import ModularBrain
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision, Observation, Reflection
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.policy.stop import StopDecision, StopReason
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.harness.composition.plan_compiler import compile_plan
from lca.harness.declarative.compile.phase.capabilities import MappingPhaseCapabilities
from lca.harness.declarative.execute.loop_guard import DeclarativeLoopGuardEvaluator
from lca.harness.declarative.lifecycle.phase_context import RestrictedPhaseContext
from lca.harness.diagnostics.doctor.compile_dry_run import ProfileCompileDryRun
from lca.harness.graph.execute.interpreter import InMemoryJournalCommitter
from lca.harness.graph.execute.subgraph_phase_runner import (
    SUBGRAPH_PHASE_RUNNER_CAPABILITY,
    SubgraphPhaseRunner,
)
from lca.harness.profile.resolve.resolve import resolve_profile
from lca.plugins.composer.runtime.runtime.factory import (
    RuntimeDeps,
    build_fixture_cognitive_runtime,
)
from lca.plugins.journal.declarative.runtime_seams_provider import (
    DefaultDeclarativeInterpreterFactory,
)
from lca.plugins.loop.control.think_guard.plugin import (
    ThinkGuardEnforceExecutor,
    ThinkGuardExecutor,
)
from lca.plugins.loop.phase.think.standard.plugin import StandardThinkExecutor
from lca.plugins.loop.phase.think.subgraph._shared import collaborators_from_brain
from lca.plugins.loop.phase.think.subgraph_host.plugin import SubgraphHostThinkExecutor
from tests.phase_executors import think_subgraph_dev_phase_executors


def _sample_decision() -> Decision:
    return Decision(
        decision_id="dec_parity_1",
        action_type="respond",
        rationale="parity fixture",
        confidence=0.9,
        response_text="hello",
    )


def _sample_response() -> LLMResponse:
    return LLMResponse(text="hello", tool_calls=[])


def _context(*, brain: Any) -> RestrictedPhaseContext:
    state = AgentState(trace_id="trace:parity", task="parity", budget=Budget())
    journal = InMemoryJournalCommitter()
    return RestrictedPhaseContext(
        plan_ref="test://parity",
        node_ref="think.main",
        state=state,
        journal=journal,
        budget=state.budget,
        artifacts={"perceive": "manifest-fixture"},
        capabilities=MappingPhaseCapabilities({"brain": brain}),
    )


def _modular_brain(*, decision: Decision, response: LLMResponse) -> ModularBrain:
    reasoner = AsyncMock()
    reasoner.generate_thoughts = AsyncMock(return_value=response)
    classifier = MagicMock()
    classifier.classify.return_value = decision
    return ModularBrain(
        reasoner=reasoner,
        classifier=classifier,
        think_pipeline=StandardCognitiveThinkPipeline(),
    )


@pytest.mark.asyncio
async def test_subgraph_host_matches_standard_with_modular_brain() -> None:
    decision = _sample_decision()
    response = _sample_response()
    brain = _modular_brain(decision=decision, response=response)
    context = _context(brain=brain)
    phase_input = PhaseInput(artifact={"perceive": "manifest-fixture"})
    patches = (
        "lca.infrastructure.session.emit.cognitive_emit.run_reasoner_generate_thoughts_with_spine_facts",
        "lca.infrastructure.session.emit.cognitive_emit.emit_brain_think_start_for_state",
        "lca.infrastructure.session.emit.cognitive_emit.emit_brain_think_end_for_state",
    )
    with (
        patch(patches[0], AsyncMock(return_value=response)),
        patch(patches[1], return_value=None),
        patch(patches[2], return_value=None),
    ):
        standard_result = await StandardThinkExecutor().execute(context, phase_input)
        host_result = await SubgraphHostThinkExecutor(
            plan_ref="bundles/think-subgraph.yaml",
            entry_node="think.subgraph.shortcut",
        ).execute(context, phase_input)

    assert standard_result.result_kind == host_result.result_kind == "decision"
    assert standard_result.payload == host_result.payload == decision


@pytest.mark.asyncio
async def test_subgraph_host_matches_standard_without_brain() -> None:
    context = _context(brain=None)
    phase_input = PhaseInput(artifact={"perceive": "manifest-fixture"})

    standard_result = await StandardThinkExecutor().execute(context, phase_input)
    host_result = await SubgraphHostThinkExecutor(
        plan_ref="bundles/think-subgraph.yaml",
        entry_node="think.subgraph.shortcut",
    ).execute(context, phase_input)

    assert standard_result.result_kind == host_result.result_kind
    assert standard_result.payload == host_result.payload


@pytest.mark.asyncio
async def test_subgraph_host_invokes_reasoner_once() -> None:
    decision = _sample_decision()
    response = _sample_response()
    brain = _modular_brain(decision=decision, response=response)
    context = _context(brain=brain)
    phase_input = PhaseInput(artifact={"perceive": "manifest-fixture"})

    with patch(
        "lca.loop.emit.cognitive.reasoner.run_reasoner_generate_thoughts_with_spine_facts",
        AsyncMock(return_value=response),
    ) as reasoner_call:
        await SubgraphHostThinkExecutor(
            plan_ref="bundles/think-subgraph.yaml",
            entry_node="think.subgraph.shortcut",
        ).execute(context, phase_input)

    reasoner_call.assert_awaited_once()
    brain.reasoner.generate_thoughts.assert_not_awaited()


@pytest.mark.asyncio
async def test_decision_payload_is_stable_across_repeated_host_runs() -> None:
    decision = _sample_decision()
    response = _sample_response()
    brain = _modular_brain(decision=decision, response=response)
    context = _context(brain=brain)
    phase_input = PhaseInput(artifact={"perceive": "manifest-fixture"})
    host = SubgraphHostThinkExecutor(
        plan_ref="bundles/think-subgraph.yaml",
        entry_node="think.subgraph.shortcut",
    )

    with patch(
        "lca.infrastructure.session.emit.cognitive_emit.run_reasoner_generate_thoughts_with_spine_facts",
        AsyncMock(return_value=response),
    ):
        first = await host.execute(context, phase_input)
        second = await host.execute(
            replace(context, state=replace(context.state, step=context.state.step + 1)),
            phase_input,
        )

    assert first.payload == second.payload == decision


def test_think_subgraph_dev_profile_compiles_and_swaps_think_binding() -> None:
    plan = compile_plan(resolve_profile("profiles/think-subgraph-dev.yaml"))
    assert plan.phase_graph is not None
    think_node = next(node for node in plan.phase_graph.nodes if node.id == "think.main")
    assert think_node.binding == "phase.think.subgraph_host"
    subgraph_plan = (
        __import__(
            "lca.harness.declarative.compile.subgraph_resolver",
            fromlist=["BundleSubgraphResolver"],
        )
        .BundleSubgraphResolver()
        .resolve("bundles/think-subgraph.yaml")
    )
    assert subgraph_plan is not None
    assert subgraph_plan.phase_graph is not None
    assert subgraph_plan.phase_graph.entry == "think.subgraph.shortcut"


def test_think_subgraph_dev_profile_passes_compile_dry_run() -> None:
    report = ProfileCompileDryRun().run("profiles/think-subgraph-dev.yaml")
    assert not any(finding.severity == "error" for finding in report.findings)


@pytest.mark.asyncio
async def test_subgraph_host_matches_cognitive_pipeline() -> None:
    decision = _sample_decision()
    response = _sample_response()
    brain = _modular_brain(decision=decision, response=response)
    context = _context(brain=brain)
    phase_input = PhaseInput(artifact={"perceive": "manifest-fixture"})
    collaborators = collaborators_from_brain(brain)
    assert collaborators is not None
    pipeline = StandardCognitiveThinkPipeline()

    with patch(
        "lca.loop.emit.cognitive.reasoner.run_reasoner_generate_thoughts_with_spine_facts",
        AsyncMock(return_value=response),
    ):
        pipeline_decision = await pipeline.decide(
            state=context.state,
            reasoner=collaborators.reasoner,
            classifier=collaborators.classifier,
            skill_router=collaborators.skill_router,
            decision_gate=collaborators.decision_gate,
            agent_gates=collaborators.agent_gates,
            reducer=collaborators.reducer,
        )
        host_result = await SubgraphHostThinkExecutor(
            plan_ref="bundles/think-subgraph.yaml",
            entry_node="think.subgraph.shortcut",
        ).execute(context, phase_input)

    assert host_result.result_kind == "decision"
    assert host_result.payload == pipeline_decision == decision


@pytest.mark.asyncio
async def test_subgraph_host_uses_injected_phase_runner() -> None:
    decision = _sample_decision()
    injected = PhaseResult(result_kind="decision", payload=decision)
    runner = MagicMock(spec=SubgraphPhaseRunner)
    runner.run_terminal_subgraph = AsyncMock(return_value=injected)
    context = RestrictedPhaseContext(
        plan_ref="test://parity",
        node_ref="think.main",
        state=AgentState(trace_id="trace:parity", task="parity", budget=Budget()),
        journal=InMemoryJournalCommitter(),
        budget=Budget(),
        artifacts={"perceive": "manifest-fixture"},
        capabilities=MappingPhaseCapabilities(
            {SUBGRAPH_PHASE_RUNNER_CAPABILITY: runner},
        ),
    )
    phase_input = PhaseInput(artifact={"perceive": "manifest-fixture"})

    result = await SubgraphHostThinkExecutor(
        plan_ref="bundles/think-subgraph.yaml",
        entry_node="think.subgraph.shortcut",
    ).execute(context, phase_input)

    runner.run_terminal_subgraph.assert_awaited_once()
    assert result is injected


@dataclass
class _RuntimeBody:
    calls: int = 0

    async def act(self, _decision: Decision, _state: AgentState) -> Observation:
        self.calls += 1
        return Observation(observation_id="observation", success=True, payload="done")


@dataclass
class _RuntimeMemory:
    updates: int = 0

    async def update(
        self,
        _state: AgentState,
        _observation: Observation,
        _reflection: Reflection,
    ) -> None:
        self.updates += 1


class _RuntimeHooks:
    async def trigger(self, _event: str, _state: AgentState, **_kwargs: object) -> None:
        return None


class _RuntimeStateStore:
    async def save(self, _state: AgentState) -> str:
        return "mem://think-subgraph-dev"


class _RuntimeArtifactClosure:
    def synthesize(self, *, fallback: str = "") -> str:
        return "[artifact closure]"


class _RuntimePerceiveHub:
    async def perceive(self, _state: AgentState) -> ContextManifest:
        return ContextManifest(items=())


class _AllowContribution:
    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                plugin_id="test.allow-contribution",
                kind=ControlVerdictKind.ALLOW,
            ),
        )


class _RuntimeStopPolicy:
    def decide(
        self,
        _state: AgentState,
        _decision: Decision,
        _observation: Observation,
        _reflection: Reflection,
    ) -> StopDecision:
        return StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="done",
            status=TaskStatus.COMPLETED,
        )


@pytest.mark.asyncio
async def test_think_subgraph_dev_runtime_executes_compiled_phase_graph() -> None:
    """End-to-end: compiled dev profile drives think.main via subgraph_host."""

    decision = Decision(
        decision_id="dec_runtime",
        action_type=ActionType.RESPOND,
        rationale="runtime fixture",
        confidence=1.0,
        response_text="done",
    )
    response = LLMResponse(text="done", tool_calls=[])
    brain = _modular_brain(decision=decision, response=response)
    body = _RuntimeBody()
    memory = _RuntimeMemory()
    perceive_hub = _RuntimePerceiveHub()
    stop_policy = _RuntimeStopPolicy()
    plan = compile_plan(resolve_profile("profiles/think-subgraph-dev.yaml"))
    interpreter_factory = DefaultDeclarativeInterpreterFactory(DeclarativeLoopGuardEvaluator())
    runner = interpreter_factory.subgraph_phase_runner()
    phase_executors = dict(think_subgraph_dev_phase_executors())
    phase_executors["control.think.guard.enforce"] = ThinkGuardEnforceExecutor()
    phase_executors["control.think.guard"] = ThinkGuardExecutor()
    allow = _AllowContribution()
    for binding in plan.phase_bindings:
        for contribution in binding.contributions:
            if contribution.executor.startswith("control.think."):
                continue
            phase_executors[contribution.executor] = allow

    with patch(
        "lca.loop.emit.cognitive.reasoner.run_reasoner_generate_thoughts_with_spine_facts",
        AsyncMock(return_value=response),
    ):
        runtime = build_fixture_cognitive_runtime(
            RuntimeDeps(
                brain=brain,
                body=body,
                memory=memory,
                hooks=_RuntimeHooks(),
                state_store=_RuntimeStateStore(),
                perceive_hub=perceive_hub,
                stop_policy=stop_policy,
                phase_capabilities={
                    "brain": brain,
                    "body": body,
                    "memory": memory,
                    "perceive_hub": perceive_hub,
                    "stop_policy": stop_policy,
                    SUBGRAPH_PHASE_RUNNER_CAPABILITY: runner,
                },
                compiled_plan=plan,
                phase_executors=phase_executors,
                artifact_closure=_RuntimeArtifactClosure(),
                interpreter_factory=interpreter_factory,
            )
        )
        result = await runtime.run("think subgraph dev runtime", max_steps=1)

    assert body.calls == 1
    assert memory.updates == 1
    assert result.status is TaskStatus.COMPLETED
    assert result.output == "done"
