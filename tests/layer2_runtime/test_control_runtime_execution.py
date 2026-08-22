from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.atoms.enums import ActionType, ReflectionVerdict
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.harness.profile.control_plan_resolver import project_control_plan
from lca.harness.profile.resolve import resolve_profile
from lca.layer2_runtime.runtime_loop import CognitiveRuntime


@dataclass
class _Brain:
    decision: Decision
    reflected: int = 0

    async def think(self, _state) -> Decision:
        return self.decision

    async def reflect(self, _state, _observation) -> Reflection:
        self.reflected += 1
        return Reflection(reflection_id="reflection", verdict=ReflectionVerdict.ON_TRACK)


@dataclass
class _Body:
    calls: int = 0

    async def act(self, _decision, _state) -> Observation:
        self.calls += 1
        return Observation(observation_id="body-observation", success=True, payload="body output")

    async def finalize(self, _observation, _state) -> None:
        return None


@dataclass
class _Memory:
    updates: int = 0

    async def perceive(self, state):
        return state

    async def update(self, _state, _observation, _reflection) -> None:
        self.updates += 1

    def query(self, _layer):
        return []


class _Hooks:
    async def trigger(self, _event: str, _state, **_kwargs) -> None:
        return None


class _StateStore:
    async def save(self, _state) -> str:
        return "mem://control-test"

    async def load(self, _state_ref: str):
        raise AssertionError("resume is not part of this test")


class _PerceiveHub:
    async def perceive(self, _state) -> ContextManifest:
        return ContextManifest(items=())


class _StopAfterTurn:
    def decide(self, _state, _decision, _observation, _reflection) -> StopDecision:
        return StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="completed",
            status=TaskStatus.COMPLETED,
        )


def _runtime(decision: Decision) -> tuple[CognitiveRuntime, _Body, _Memory]:
    body = _Body()
    memory = _Memory()
    runtime = CognitiveRuntime(
        brain=_Brain(decision),
        body=body,
        memory=memory,
        hooks=_Hooks(),
        state_store=_StateStore(),
        stop_rule=_StopAfterTurn(),
        perceive_hub=_PerceiveHub(),
        control_plan=project_control_plan(resolve_profile("profiles/web-standard.yaml")),
    )
    return runtime, body, memory


@pytest.mark.asyncio
async def test_authorization_verdict_blocks_body_execution() -> None:
    runtime, body, memory = _runtime(
        Decision(
            decision_id="malformed-tool",
            action_type=ActionType.USE_TOOL,
            rationale="tool without call",
            confidence=1.0,
        )
    )

    await runtime.run("test control block", max_steps=1)

    assert body.calls == 0
    assert memory.updates == 1


@pytest.mark.asyncio
async def test_safe_boundary_stop_prevents_body_execution() -> None:
    runtime, body, memory = _runtime(
        Decision(
            decision_id="explicit-stop",
            action_type=ActionType.STOP,
            rationale="stop before body",
            confidence=1.0,
        )
    )

    result = await runtime.run("test control stop", max_steps=1)

    assert body.calls == 0
    assert memory.updates == 0
    assert result.status is TaskStatus.FAILED
    assert result.error is None


@pytest.mark.asyncio
async def test_allowed_decision_reaches_body_and_memory() -> None:
    runtime, body, memory = _runtime(
        Decision(
            decision_id="valid-response",
            action_type=ActionType.RESPOND,
            rationale="return answer",
            confidence=1.0,
            response_text="completed",
        )
    )

    result = await runtime.run("test allowed execution", max_steps=1)

    assert body.calls == 1
    assert memory.updates == 1
    assert result.status is TaskStatus.COMPLETED
