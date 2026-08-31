from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.atoms.enums import ActionType, ReflectionVerdict
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseInput, PhaseResult
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from lca.plugins.composer.runtime.runtime_factory import (
    RuntimeDeps,
    build_fixture_cognitive_runtime,
)
from tests.phase_executors import standard_phase_executors


@dataclass
class _Brain:
    async def think(self, _state) -> Decision:
        return Decision(
            decision_id="decision",
            action_type=ActionType.RESPOND,
            rationale="fixture",
            confidence=1.0,
            response_text="done",
        )

    async def reflect(self, _state, _observation) -> Reflection:
        return Reflection(reflection_id="reflection", verdict=ReflectionVerdict.ON_TRACK)


@dataclass
class _Body:
    calls: int = 0

    async def act(self, _decision, _state) -> Observation:
        self.calls += 1
        return Observation(observation_id="observation", success=True, payload="done")


@dataclass
class _Memory:
    updates: int = 0

    async def update(self, _state, _observation, _reflection) -> None:
        self.updates += 1


class _Hooks:
    async def trigger(self, _event: str, _state, **_kwargs) -> None:
        return None


class _StateStore:
    async def save(self, _state) -> str:
        return "mem://declarative"


class _ArtifactClosure:
    def synthesize(self, *, fallback: str = "") -> str:
        return "[artifact closure]"


class _PerceiveHub:
    async def perceive(self, _state) -> ContextManifest:
        return ContextManifest(items=())


class _AllowContribution:
    async def execute(self, _context, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                plugin_id="test.allow-contribution",
                kind=ControlVerdictKind.ALLOW,
            ),
        )


class _Stop:
    def decide(self, _state, _decision, _observation, _reflection) -> StopDecision:
        return StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="done",
            status=TaskStatus.COMPLETED,
        )


@pytest.mark.asyncio
async def test_cognitive_runtime_executes_compiled_phase_graph() -> None:
    plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
    body = _Body()
    memory = _Memory()
    brain = _Brain()
    perceive_hub = _PerceiveHub()
    stop_policy = _Stop()
    phase_executors = dict(standard_phase_executors())
    allow = _AllowContribution()
    for binding in plan.phase_bindings:
        for contribution in binding.contributions:
            phase_executors[contribution.executor] = allow
    runtime = build_fixture_cognitive_runtime(
        RuntimeDeps(
            brain=brain,
            body=body,
            memory=memory,
            hooks=_Hooks(),
            state_store=_StateStore(),
            stop_policy=stop_policy,
            perceive_hub=perceive_hub,
            phase_capabilities={
                "brain": brain,
                "body": body,
                "memory": memory,
                "perceive_hub": perceive_hub,
                "stop_policy": stop_policy,
            },
            compiled_plan=plan,
            phase_executors=phase_executors,
            artifact_closure=_ArtifactClosure(),
        )
    )

    result = await runtime.run("declarative runtime", max_steps=1)

    assert body.calls == 1
    assert memory.updates == 1
    assert result.status is TaskStatus.COMPLETED
    assert result.output == "done\n\n[artifact closure]"
