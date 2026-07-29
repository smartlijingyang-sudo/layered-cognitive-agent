"""Architecture deepening acceptance tests — drive shipped entry points."""

from __future__ import annotations

import pytest

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.enums import ActionType, ReflectionVerdict, TeamProcess
from lca.contracts.ids import new_id
from lca.contracts.lifecycle import AgentCard, TaskStatus
from lca.contracts.protocols import LLMAdapter
from lca.contracts.result import UnregisteredActionError
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.state import Budget, TypedState
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer1_cognitive.body.action_handlers import RespondOperation
from lca.layer1_cognitive.body.action_registry import ActionRegistry
from lca.layer1_cognitive.body.fallback_decorated_body import FallbackDecoratedBody
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.brain.candidate_evaluation_pipeline import (
    SimpleCandidateEvaluationPipeline,
)
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner
from lca.layer1_cognitive.brain.skill_router import StaticSkillRouter
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry
from lca.layer1_cognitive.prompt_manager import SimplePromptManager
from lca.layer2_runtime.fallback_handler import FallbackActionPolicy
from lca.layer2_runtime.loop_judge import DefaultLoopJudge
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStepOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer4_app.api import Agent, MultiAgentTeam


def _state() -> TypedState:
    return TypedState(trace_id="t", task="task", budget=Budget())


class TestLifecycleTwins:
    def test_single_agent_card_definition(self) -> None:
        import lca.contracts.decision as decision_mod
        import lca.contracts.lifecycle as life_mod

        assert decision_mod.AgentCard is life_mod.AgentCard
        assert not hasattr(decision_mod, "TaskStatus")
        card = AgentCard(agent_id="a1", role="r", capabilities=[])
        assert card.protocols_supported[0].value == "internal"


class TestDegradationFirstClass:
    async def test_unregistered_raises_typed_error(self) -> None:
        body = SimpleBody(action_registry=ActionRegistry())
        decision = StructuredDecision(
            decision_id="d",
            action_type="invented",
            rationale="x",
            confidence=0.5,
            response_text="hello",
        )
        with pytest.raises(UnregisteredActionError) as ei:
            await body.act(decision, _state())
        assert ei.value.action_type == "invented"

    async def test_fallback_sets_degraded_from_and_policy_stops(self) -> None:
        registry = ActionRegistry()
        registry.register(ActionType.RESPOND, RespondOperation())
        body = FallbackDecoratedBody(
            inner=SimpleBody(action_registry=registry),
            fallback_handler=FallbackActionPolicy(),
        )
        decision = StructuredDecision(
            decision_id="d",
            action_type="research_plan",
            rationale="llm invented",
            confidence=0.7,
            response_text="valid answer body",
        )
        state = _state()
        obs = await body.act(decision, state)
        assert obs.success is True
        assert obs.degraded_from == "research_plan"
        reflection = Reflection(reflection_id="r", verdict=ReflectionVerdict.ON_TRACK)
        outcome = DefaultStepOutcomePolicy().resolve(state, decision, obs, reflection)
        assert outcome.should_stop is True
        assert outcome.final_output == "valid answer body"


class TestCheckpointResume:
    async def test_checkpoint_persists_via_state_store(self) -> None:
        store = InMemoryStateStore()

        class _Mem:
            async def perceive_and_retrieve(self, s: TypedState) -> TypedState:
                return s

            async def update_multi_level(
                self, s: TypedState, o: Observation, r: Reflection
            ) -> None:
                return None

        class _Brain:
            async def think(self, s: TypedState) -> StructuredDecision:
                return StructuredDecision(
                    decision_id=new_id("d"),
                    action_type=ActionType.RESPOND,
                    rationale="done",
                    confidence=1.0,
                    response_text="DONE",
                )

            async def reflect(self, s: TypedState, o: Observation) -> Reflection:
                return Reflection(reflection_id=new_id("r"), verdict=ReflectionVerdict.ON_TRACK)

        class _Body:
            async def act(self, d: StructuredDecision, s: TypedState) -> Observation:
                return Observation(
                    observation_id=new_id("o"), success=True, payload=d.response_text
                )

            def bind_transport(self, t: object) -> None:
                return None

        rt = CognitiveRuntime(
            brain=_Brain(),  # type: ignore[arg-type]  # 测试用内部类满足 Protocol 结构
            body=_Body(),  # type: ignore[arg-type]  # 测试用内部类满足 Protocol 结构
            memory=_Mem(),  # type: ignore[arg-type]  # 测试用内部类满足 Protocol 结构
            hooks=SimpleHookRegistry(ConsoleObservability()),
            state_store=store,
            judge=DefaultLoopJudge(outcome_policy=DefaultStepOutcomePolicy()),
        )
        result = await rt.run("checkpoint me", max_steps=3)
        assert result.status == TaskStatus.COMPLETED
        assert any(k.startswith("mem://") for k in store._store)


class TestSkillRouterTemplate:
    async def test_reasoner_uses_active_template(self) -> None:
        recorded: list[str] = []

        class CapturingLLM(LLMAdapter):
            name = "cap"

            async def complete(self, prompt: str, **kwargs: object) -> str:
                recorded.append(prompt)
                return (
                    '{"action_type":"respond","response_text":"ok",'
                    '"rationale":"r","confidence":0.9}'
                )

            async def stream(self, prompt: str, **kwargs: object):  # type: ignore[no-untyped-def]  # kwargs 类型由 Protocol 约束
                yield await self.complete(prompt)

        pm = SimplePromptManager()
        pm.register_template(
            "custom_research",
            "TEMPLATE_MARKER_RESEARCH\nROLE: {role}\nTASK: {task}\n"
            "{tools}\n{context}\n{allowed_actions}\n{goal}\n{backstory}",
        )
        pm.register_template("react_prompt", load_builtin_prompt("react_prompt"))
        rp = RoleProfile(
            role="研究员",
            goal="g",
            backstory="b",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        brain = ModularBrain(
            reasoner=SimpleReasoner(CapturingLLM(), pm, rp, tools_desc="none"),
            decision_parser=SimpleDecisionParser(),
            critic=SimpleCritic(),
            evaluation_pipeline=SimpleCandidateEvaluationPipeline(),
            skill_router=StaticSkillRouter("custom_research"),
        )
        state = _state()
        state.task = "研究市场"
        decision = await brain.think(state)
        assert state.active_template == "custom_research"
        assert recorded and "TEMPLATE_MARKER_RESEARCH" in recorded[0]
        assert decision.action_type in (ActionType.RESPOND, "respond")


class TestDebateMultiRound:
    async def test_default_debate_runs_multiple_rounds_on_disagreement(self) -> None:
        class DebateLLM(LLMAdapter):
            name = "debate"

            async def complete(self, prompt: str, **kwargs: object) -> str:
                import json
                import re

                role_m = re.search(r"ROLE:\s*([^\n]+)", prompt)
                role = role_m.group(1).strip() if role_m else ""
                converging = "Previous proposals" in prompt
                if not converging:
                    price = 39.9 if "保守" in role else 59.9
                    return json.dumps(
                        {
                            "action_type": "respond",
                            "response_text": f"PROPOSAL: ${price}",
                            "confidence": 0.7,
                        }
                    )
                return json.dumps(
                    {
                        "action_type": "respond",
                        "response_text": "PROPOSAL: $49.9 折衷",
                        "confidence": 0.9,
                    }
                )

            async def stream(self, prompt: str, **kwargs: object):  # type: ignore[no-untyped-def]  # kwargs 类型由 Protocol 约束
                yield await self.complete(prompt)

        llm = DebateLLM()
        a = Agent(role="保守派定价", goal="", backstory="", tools=[], llm=llm, max_steps=2)
        b = Agent(role="激进派定价", goal="", backstory="", tools=[], llm=llm, max_steps=2)
        team = MultiAgentTeam(members=[a, b], process=TeamProcess.DEBATE, max_rounds=3)
        result = await team.run("请定价")
        assert result.status == TaskStatus.COMPLETED
        assert result.total_steps >= 2


class TestActionRegistryProtocolImport:
    def test_protocol_from_contracts(self) -> None:
        assert isinstance(ActionRegistry(), ActionRegistryProtocol)

    def test_no_pass_through_builder_in_handlers(self) -> None:
        import lca.layer1_cognitive.body.action_handlers as ah

        assert not hasattr(ah, "build_default_action_registry")
