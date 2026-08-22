from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.declarative_phase_graph import (
    ContributionRole,
    PhaseContribution,
    PhaseResult,
    SemanticPhase,
)
from lca.harness.declarative import GraphAssembler, MappingRestrictedScope
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from lca.layer2_runtime.declarative_runtime import (
    DeclarativeRuntimeDriver,
    RuntimePhaseCapabilities,
)
from lca.layer2_runtime.reducer import DefaultReducer


class _StateStore:
    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}
        self._index = 0

    async def save(self, state: AgentState) -> str:
        self._index += 1
        reference = f"state://{self._index}"
        self._states[reference] = state
        return reference

    async def load(self, state_ref: str) -> AgentState:
        return self._states[state_ref]


class _Hooks:
    async def trigger(self, *_args, **_kwargs) -> None:
        return None


class _Executor:
    def __init__(self, phase: SemanticPhase) -> None:
        self.phase = phase

    async def execute(self, _context, _input) -> PhaseResult:
        if self.phase is SemanticPhase.PERCEIVE:
            return PhaseResult(result_kind="context", payload={})
        if self.phase is SemanticPhase.THINK:
            return PhaseResult(
                result_kind="decision", payload=SimpleNamespace(decision_id="decision:driver")
            )
        if self.phase is SemanticPhase.ACT:
            return PhaseResult(result_kind="observation", payload={"ok": True})
        if self.phase is SemanticPhase.REFLECT:
            return PhaseResult(result_kind="reflection", payload={})
        if self.phase is SemanticPhase.REMEMBER:
            return PhaseResult(result_kind="write_set", payload={})
        from lca.contracts.models.core.lifecycle import TaskStatus
        from lca.contracts.models.core.stop import StopDecision, StopReason
        from lca.contracts.protocols.command_envelope import RunDelta

        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            status=TaskStatus.COMPLETED,
            final_output="resumed",
        )
        return PhaseResult(
            result_kind="stop_decision",
            payload=stop,
            deltas=(RunDelta(metadata={"operation": "stop", "stop": stop}),),
        )


class _PauseOnce:
    def __init__(self) -> None:
        self._calls = 0

    async def execute(self, _context, _input) -> PhaseResult:
        self._calls += 1
        if self._calls == 1:
            return PhaseResult(result_kind="policy", payload={"verdict": "pause"})
        return PhaseResult(result_kind="policy", payload={"verdict": "allow"})


@pytest.mark.asyncio
async def test_driver_resumes_a_paused_cursor_through_the_same_declarative_plan() -> None:
    standard_plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
    pause = PhaseContribution(
        phase=SemanticPhase.THINK,
        role=ContributionRole.GOVERN,
        executor="control.pause.once",
        output="control.pause",
        aggregation="first-terminal",
    )
    plan = replace(
        standard_plan,
        phase_bindings=tuple(
            replace(binding, contributions=(*binding.contributions, pause))
            if binding.semantic_phase is SemanticPhase.THINK
            else binding
            for binding in standard_plan.phase_bindings
        ),
    )
    executors = {
        **{f"phase.{phase.value}.standard": _Executor(phase) for phase in SemanticPhase},
        "control.pause.once": _PauseOnce(),
    }
    # Force early assembly to make the test exercise the same capability map as the driver.
    GraphAssembler().assemble(plan, MappingRestrictedScope(executors))
    driver = DeclarativeRuntimeDriver(
        plan=plan,
        phase_executors=executors,
        capabilities=RuntimePhaseCapabilities(
            brain=None, body=None, memory=None, perceive_hub=None, stop_rule=None
        ),
        reducer=DefaultReducer(),
        hooks=_Hooks(),
        state_store=_StateStore(),
    )
    initial = AgentState(trace_id="trace:driver", task="resume", budget=create_budget(max_steps=4))

    paused = await driver.run(initial)

    assert paused.status is TaskStatus.INPUT_REQUIRED
    checkpoint = paused.extra["declarative_checkpoint"]

    resumed = await driver.resume(checkpoint, input="approved")

    assert resumed.status is TaskStatus.COMPLETED
    assert resumed.extra["outcome"] == "completed"
