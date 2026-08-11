"""Architecture deepening acceptance tests — drive shipped entry points."""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums import ActionType, LLMStreamEventType, ReflectionVerdict
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.lifecycle import AgentCard, TaskStatus
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.models.core.result import UnregisteredActionError
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.models.team.team_coordination import Debate
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.action import ActionRegistryProtocol
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer1_cognitive.body.action_registry import ActionRegistry
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt
from lca.layer1_cognitive.brain.reasoner import PromptReasoner
from lca.layer1_cognitive.brain.skill_router import StaticSkillRouter
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry
from lca.layer2_runtime.default_stop_rule import DefaultStopRule
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer4_app.api import Agent, Team


def _state() -> AgentState:
    return AgentState(trace_id="t", task="task", budget=Budget())


class TestLifecycleTwins:
    def test_single_agent_card_definition(self) -> None:
        import lca.contracts.models.core.decision as decision_mod
        import lca.contracts.models.core.lifecycle as life_mod

        assert decision_mod.AgentCard is life_mod.AgentCard
        assert not hasattr(decision_mod, "TaskStatus")
        card = AgentCard(agent_id="a1", role="r", capabilities=[])
        assert card.protocols_supported[0].value == "internal"


class TestDegradationFirstClass:
    async def test_unregistered_raises_typed_error(self) -> None:
        body = SimpleBody(action_registry=ActionRegistry())
        decision = Decision(
            decision_id="d",
            action_type="invented",
            rationale="x",
            confidence=0.5,
            response_text="hello",
        )
        with pytest.raises(UnregisteredActionError) as ei:
            await body.act(decision, _state())
        assert ei.value.action_type == "invented"


class TestCheckpointResume:
    async def test_checkpoint_persists_via_state_store(self) -> None:
        store = InMemoryStateStore()

        class _Mem:
            async def perceive(self, s: AgentState) -> AgentState:
                return s

            async def update(self, s: AgentState, o: Observation, r: Reflection) -> None:
                return None

        class _Brain:
            async def think(self, s: AgentState) -> Decision:
                return Decision(
                    decision_id=new_id("d"),
                    action_type=ActionType.RESPOND,
                    rationale="done",
                    confidence=1.0,
                    response_text="DONE",
                )

            async def reflect(self, s: AgentState, o: Observation) -> Reflection:
                return Reflection(reflection_id=new_id("r"), verdict=ReflectionVerdict.ON_TRACK)

        class _Body:
            async def act(self, d: Decision, s: AgentState) -> Observation:
                return Observation(
                    observation_id=new_id("o"), success=True, payload=d.response_text
                )

            def bind_channel(self, t: object) -> None:
                return None

        rt = CognitiveRuntime(
            brain=_Brain(),  # type: ignore[arg-type]  # 测试用内部类满足 Protocol 结构
            body=_Body(),  # type: ignore[arg-type]  # 测试用内部类满足 Protocol 结构
            memory=_Mem(),  # type: ignore[arg-type]  # 测试用内部类满足 Protocol 结构
            hooks=SimpleHookRegistry(),
            state_store=store,
            stop_rule=DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy()),
        )
        result = await rt.run("checkpoint me", max_steps=3)
        assert result.status == TaskStatus.COMPLETED
        assert any(k.startswith("mem://") for k in store._store)


class TestSkillRouterTemplate:
    async def test_reasoner_uses_active_template(self) -> None:
        recorded: list[str] = []

        class CapturingLLM(LLMAdapter):
            name = "cap"

            async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
                recorded.append(prompt)
                return LLMResponse(
                    text='{"action_type":"respond","response_text":"ok",'
                    '"rationale":"r","confidence":0.9}'
                )

            async def stream(self, prompt: str, **kwargs: object):  # type: ignore[no-untyped-def]  # kwargs 类型由 Protocol 约束
                response = await self.complete(prompt, **kwargs)
                yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=response.text)
                yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)

        rp = RoleProfile(
            role="研究员",
            goal="g",
            backstory="b",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        brain = ModularBrain(
            reasoner=PromptReasoner(
                CapturingLLM(),
                rp,
                tools_desc="none",
                templates={
                    "custom_research": "TEMPLATE_MARKER_RESEARCH\nROLE: {role}\nTASK: {task}\n"
                    "{tools}\n{context}\n{goal}\n{backstory}",
                    "react_prompt": load_builtin_prompt("react_prompt"),
                },
            ),
            critic=SimpleCritic(),
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

            async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
                import json
                import re

                role_m = re.search(r"ROLE:\s*([^\n]+)", prompt)
                role = role_m.group(1).strip() if role_m else ""
                converging = "Previous proposals" in prompt
                if not converging:
                    price = 39.9 if "保守" in role else 59.9
                    return LLMResponse(
                        text=json.dumps(
                            {
                                "action_type": "respond",
                                "response_text": f"PROPOSAL: ${price}",
                                "confidence": 0.7,
                            }
                        )
                    )
                return LLMResponse(
                    text=json.dumps(
                        {
                            "action_type": "respond",
                            "response_text": "PROPOSAL: $49.9 折衷",
                            "confidence": 0.9,
                        }
                    )
                )

            async def stream(self, prompt: str, **kwargs: object):  # type: ignore[no-untyped-def]  # kwargs 类型由 Protocol 约束
                response = await self.complete(prompt, **kwargs)
                yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=response.text)
                yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)

        llm = DebateLLM()
        a = Agent(role="保守派定价", goal="", backstory="", tools=[], llm=llm, max_steps=2)
        b = Agent(role="激进派定价", goal="", backstory="", tools=[], llm=llm, max_steps=2)
        team = Team(members=[a, b], coordination=Debate(max_rounds=3))
        result = await team.run("请定价")
        assert result.status == TaskStatus.COMPLETED
        assert result.total_steps >= 2


class TestActionRegistryProtocolImport:
    def test_protocol_from_contracts(self) -> None:
        assert isinstance(ActionRegistry(), ActionRegistryProtocol)

    def test_no_pass_through_builder_in_handlers(self) -> None:
        import lca.layer1_cognitive.body.action_handlers as ah

        assert not hasattr(ah, "build_default_action_registry")
