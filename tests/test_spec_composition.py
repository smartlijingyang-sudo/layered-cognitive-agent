"""ADR-0033 行为守护 —— 门面协议化 / spec 声明式组合 / 显式 composer。"""

from __future__ import annotations

import unittest

from lca.application.api import Agent, Team, TeamLead
from lca.cognition.memory.simple_memory import SimpleMemorySystem
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, Reflection
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.team_coordination import LeadMandate, Pipeline
from lca.contracts.protocols import AgentUnit, Brain, TeamUnit
from lca.contracts.protocols.journal.spec import AgentSpec, LeadSpec
from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter


class _StubBrain(Brain):
    """最小 Brain 实例 —— 用于验证 spec 中的 brain 实例在重组后不丢失。"""

    async def think(self, state: AgentState):
        return Decision(
            decision_id=new_id("dec"),
            action_type="respond",
            rationale="stub",
            confidence=1.0,
            response_text="stub",
        )

    async def reflect(self, state, observation):
        return Reflection(reflection_id="r", verdict="on_track")


def _agent(**overrides) -> Agent:
    kwargs = {
        "role": "worker",
        "goal": "g",
        "backstory": "b",
        "tools": [],
        "llm": MockLLMAdapter(),
    }
    kwargs.update(overrides)
    return Agent(**kwargs)


class TestFacadeProtocolConformance(unittest.TestCase):
    """L4 门面必须落在 contracts 协议体系内（ADR-0033）。"""

    def test_agent_satisfies_agent_unit(self) -> None:
        self.assertIsInstance(_agent(), AgentUnit)

    def test_team_satisfies_team_unit(self) -> None:
        team = Team(members=[_agent()], coordination=Pipeline())
        self.assertIsInstance(team, TeamUnit)

    def test_agent_exposes_role_profile(self) -> None:
        agent = _agent(role="分析师")
        self.assertEqual(agent.role_profile.role, "分析师")

    def test_team_lead_holds_lead_spec(self) -> None:
        lead = TeamLead.board(_agent(role="pm"))
        self.assertIsInstance(lead.spec, LeadSpec)
        self.assertIs(lead.mandate, LeadMandate.BOARD)
        self.assertIsInstance(lead.spec.agent, AgentSpec)


class TestSpecFaithfulRecomposition(unittest.IsolatedAsyncioTestCase):
    """Team 重组必须无损保留 spec 中的显式选择（旧实现会丢失自定义组件）。"""

    async def test_member_keeps_custom_memory_and_brain_instances(self) -> None:
        memory = SimpleMemorySystem()
        brain = _StubBrain()
        agent = _agent(memory=memory, brain=brain)
        team = Team(members=[agent], coordination=Pipeline())
        member = team._handle.members[0]  # type: ignore[attr-defined]
        self.assertIs(member.runtime.memory.inner, memory)  # type: ignore[attr-defined]
        self.assertIs(member.runtime.brain, brain)  # type: ignore[attr-defined]

    async def test_member_keeps_budget(self) -> None:
        agent = _agent(max_steps=7)
        team = Team(members=[agent], coordination=Pipeline())
        member = team._handle.members[0]  # type: ignore[attr-defined]
        self.assertEqual(member.max_steps, 7)


class TestExplicitComposerInjection(unittest.IsolatedAsyncioTestCase):
    """自定义注册必须经显式 composer 贯通 Agent 与 Team（无隐式全局）。"""

    async def test_custom_memory_flows_through_team(self) -> None:
        from lca.application.api import get_or_create_default_ctx

        ctx = get_or_create_default_ctx()
        ctx.inject("memory").register("custom", SimpleMemorySystem)
        agent = _agent(memory="custom", scope=ctx)
        team = Team(
            members=[agent],
            coordination=Pipeline(),
            scope=ctx,
        )
        member = team._handle.members[0]  # type: ignore[attr-defined]
        self.assertIsInstance(member.runtime.memory.inner, SimpleMemorySystem)  # type: ignore[attr-defined]

    async def test_unknown_component_without_composer_raises(self) -> None:
        from lca.contracts.mechanisms.capability import MissingCapabilityError

        with self.assertRaises(MissingCapabilityError):
            _agent(memory="custom_not_registered")
