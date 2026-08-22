from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.atoms.enums import ActionType, ReflectionVerdict
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.declarative_phase_graph import SemanticPhase
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.plugins.control_contributions.standard import StandardControlContribution
from lca.plugins.effect_handlers.body_act import BodyActEffectHandler
from lca.plugins.effect_handlers.memory_update import MemoryUpdateEffectHandler
from lca.plugins.phase_executors.common import StandardPhaseExecutor


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


class _PerceiveHub:
    async def perceive(self, _state) -> ContextManifest:
        return ContextManifest(items=())


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
    runtime = CognitiveRuntime(
        brain=_Brain(),
        body=body,
        memory=memory,
        hooks=_Hooks(),
        state_store=_StateStore(),
        stop_rule=_Stop(),
        perceive_hub=_PerceiveHub(),
        compiled_plan=plan,
        phase_executors={
            **{
                f"phase.{phase.value}.standard": StandardPhaseExecutor(phase)
                for phase in SemanticPhase
            },
            "control.standard": StandardControlContribution(),
        },
        effect_handlers={
            "body.act": BodyActEffectHandler(),
            "memory.update": MemoryUpdateEffectHandler(),
        },
    )

    result = await runtime.run("declarative runtime", max_steps=1)

    assert body.calls == 1
    assert memory.updates == 1
    assert result.status is TaskStatus.COMPLETED
