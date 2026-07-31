"""验证所有实现类显式满足对应 Protocol 的 isinstance 断言。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.protocols import (
    AgentTransport,
    AgentUnit,
    Body,
    Brain,
    Critic,
    DecisionParser,
    EventBus,
    Hook,
    HookRegistry,
    LLMAdapter,
    MemorySystem,
    Observability,
    PromptManager,
    Reasoner,
    Runtime,
    SafeExecutor,
    StateStore,
    TeamUnit,
    Tool,
    ToolRegistry,
)
from lca.layer0_infra.llm_adapter.anthropic_llm import AnthropicLLMAdapter

# L0
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer0_infra.tools.calculator_tool import CalculatorTool
from lca.layer0_infra.tools.weather_tool import WeatherTool
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.transport_registry import (
    UnimplementedTransport,
)
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry

# L1
from lca.layer1_cognitive.brain.candidate_evaluation_pipeline import (
    SimpleCandidateEvaluationPipeline,
)
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.prompt_manager import SimplePromptManager
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner
from lca.layer1_cognitive.event_bus import SimpleEventBus
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem

# L2
from lca.layer2_runtime.default_loop_judge import DefaultStopRule
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStepOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime

# L3
from lca.layer3_agent.simple_agent import CognitiveAgent


class TestL0ProtocolCompliance(unittest.TestCase):
    """L0 基础设施层：所有实现类满足对应 Protocol。"""

    def test_mock_llm_is_llm_adapter(self):
        self.assertIsInstance(MockLLMAdapter(), LLMAdapter)

    def test_openai_compat_is_llm_adapter(self):
        self.assertIsInstance(OpenAICompatAdapter.__new__(OpenAICompatAdapter), LLMAdapter)

    def test_anthropic_is_llm_adapter(self):
        self.assertIsInstance(AnthropicLLMAdapter.__new__(AnthropicLLMAdapter), LLMAdapter)

    def test_calculator_is_tool(self):
        self.assertIsInstance(CalculatorTool(), Tool)

    def test_weather_is_tool(self):
        self.assertIsInstance(WeatherTool(), Tool)

    def test_console_observability(self):
        self.assertIsInstance(ConsoleObservability(), Observability)

    def test_in_memory_state_store(self):
        self.assertIsInstance(InMemoryStateStore(), StateStore)

    def test_internal_transport(self):
        self.assertIsInstance(InternalTransport(), AgentTransport)

    def test_internal_transport_protocol_name(self):
        self.assertEqual(InternalTransport().protocol_name, "internal")

    def test_unimplemented_transport_is_agent_transport(self):
        self.assertIsInstance(UnimplementedTransport("a2a"), AgentTransport)

    def test_unimplemented_transport_protocol_name(self):
        t = UnimplementedTransport("mcp")
        self.assertEqual(t.protocol_name, "mcp")

    def test_default_registry_resolves_all_delegation_protocols(self):
        """DelegationSpec.protocol 的每个取值都能在默认 registry 中 resolve 到非空实现。"""
        from lca.layer4_app.assembly import build_default_transport_registry

        registry = build_default_transport_registry()
        for protocol in ("internal", "a2a", "mcp"):
            transport = registry.resolve(protocol)
            self.assertIsNotNone(transport, f"protocol {protocol!r} 未注册")


class TestL1ProtocolCompliance(unittest.TestCase):
    """L1 认知层：所有实现类满足对应 Protocol。"""

    def _build_brain_deps(self):
        """构建 ModularBrain 所需的依赖。"""
        from lca.contracts.role_team import RoleProfile, ToolPermissionManifest

        llm = MockLLMAdapter()
        pm = SimplePromptManager()
        pm.register_template("react_prompt", "test")
        rp = RoleProfile(
            role="t",
            goal="t",
            backstory="t",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        reasoner = SimpleReasoner(llm, pm, rp, "(无)")
        return reasoner

    def test_modular_brain_is_brain_strategy(self):
        reasoner = self._build_brain_deps()
        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(),
            critic=SimpleCritic(),
            evaluation_pipeline=SimpleCandidateEvaluationPipeline(),
        )
        self.assertIsInstance(brain, Brain)

    def test_simple_reasoner(self):
        reasoner = self._build_brain_deps()
        self.assertIsInstance(reasoner, Reasoner)

    def test_simple_decision_parser(self):
        self.assertIsInstance(SimpleDecisionParser(), DecisionParser)

    def test_simple_critic(self):
        self.assertIsInstance(SimpleCritic(), Critic)

    def test_simple_body(self):
        tool_reg = SimpleToolRegistry()
        obs = ConsoleObservability()
        from lca.contracts.role_team import ToolPermissionManifest

        executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]), obs)
        body = SimpleBody(tool_reg, executor)
        self.assertIsInstance(body, Body)

    def test_simple_tool_registry(self):
        self.assertIsInstance(SimpleToolRegistry(), ToolRegistry)

    def test_simple_safe_executor(self):
        obs = ConsoleObservability()
        from lca.contracts.role_team import ToolPermissionManifest

        executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]), obs)
        self.assertIsInstance(executor, SafeExecutor)

    def test_simple_memory_system(self):
        self.assertIsInstance(SimpleMemorySystem(), MemorySystem)

    def test_simple_event_bus(self):
        self.assertIsInstance(SimpleEventBus(), EventBus)

    def test_simple_prompt_manager(self):
        self.assertIsInstance(SimplePromptManager(), PromptManager)

    def test_simple_hook_registry(self):
        obs = ConsoleObservability()
        self.assertIsInstance(SimpleHookRegistry(obs), HookRegistry)

    def test_default_logging_hook_is_hook(self):
        self.assertIsInstance(default_logging_hook, Hook)


class TestL2ProtocolCompliance(unittest.TestCase):
    """L2 运行时层。"""

    def test_cognitive_runtime_is_runtime(self):
        from lca.contracts.role_team import RoleProfile, ToolPermissionManifest

        llm = MockLLMAdapter()
        pm = SimplePromptManager()
        pm.register_template("react_prompt", "test")
        rp = RoleProfile(
            role="t",
            goal="t",
            backstory="t",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        reasoner = SimpleReasoner(llm, pm, rp, "(无)")
        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(),
            critic=SimpleCritic(),
            evaluation_pipeline=SimpleCandidateEvaluationPipeline(),
        )
        obs = ConsoleObservability()
        body = SimpleBody(
            SimpleToolRegistry(),
            SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]), obs),
        )
        runtime = CognitiveRuntime(
            brain,
            body,
            SimpleMemorySystem(),
            SimpleHookRegistry(obs),
            InMemoryStateStore(),
            judge=DefaultStopRule(outcome_policy=DefaultStepOutcomePolicy()),
        )
        self.assertIsInstance(runtime, Runtime)


class TestL3ProtocolCompliance(unittest.TestCase):
    """L3 Agent 层。"""

    def _build_agent(self):
        from lca.contracts.role_team import RoleProfile, ToolPermissionManifest

        llm = MockLLMAdapter()
        pm = SimplePromptManager()
        pm.register_template("react_prompt", "test")
        rp = RoleProfile(
            role="t",
            goal="t",
            backstory="t",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        reasoner = SimpleReasoner(llm, pm, rp, "(无)")
        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(),
            critic=SimpleCritic(),
            evaluation_pipeline=SimpleCandidateEvaluationPipeline(),
        )
        obs = ConsoleObservability()
        body = SimpleBody(
            SimpleToolRegistry(),
            SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]), obs),
        )
        runtime = CognitiveRuntime(
            brain,
            body,
            SimpleMemorySystem(),
            SimpleHookRegistry(obs),
            InMemoryStateStore(),
            judge=DefaultStopRule(outcome_policy=DefaultStepOutcomePolicy()),
        )
        return CognitiveAgent(runtime, rp), rp, runtime

    def test_agent_is_agent_runtime(self):
        agent, _, _ = self._build_agent()
        self.assertIsInstance(agent, AgentUnit)

    def test_supervisor_is_agent_runtime(self):
        _, rp, runtime = self._build_agent()
        sup = CognitiveAgent(runtime, rp, max_steps=20, max_wall_clock_seconds=300)
        self.assertIsInstance(sup, AgentUnit)

    def test_team_orchestrator_is_team_runtime(self):
        from lca.contracts.role_team import TeamConfig
        from lca.layer3_agent.team_orchestrator import TeamOrchestrator

        agent, _rp, _runtime = self._build_agent()
        config = TeamConfig(process="sequential")
        orchestrator = TeamOrchestrator([agent], config)
        self.assertIsInstance(orchestrator, TeamUnit)


class TestBrainFactoryRegistryIntegration(unittest.TestCase):
    """验证 BrainFactoryRegistry 动态选择 Brain 策略。"""

    def test_default_strategy_registered(self):
        from lca.layer2_runtime.strategy_registry import get_global_brain_factory_registry

        reg = get_global_brain_factory_registry()
        self.assertIn("default", reg.list_strategies())

    def test_agent_with_string_strategy(self):
        from lca.layer4_app.api import Agent

        agent = Agent(
            role="测试",
            goal="测试",
            backstory="测试",
            tools=[CalculatorTool()],
            llm=MockLLMAdapter(),
            brain_strategy="default",
        )
        result = asyncio.run(agent.run("1 + 2"))
        self.assertEqual(result.status, "completed")

    def test_agent_with_custom_strategy(self):
        from lca.contracts.decision import Reflection
        from lca.contracts.state import AgentState
        from lca.layer4_app.api import Agent

        class StubBrain(Brain):
            async def think(self, state: AgentState):
                return SimpleDecisionParser().parse(
                    '{"action_type":"respond","response_text":"stub","confidence":1.0}',
                    state,
                )

            async def reflect(self, state, observation):
                return Reflection(reflection_id="r", verdict="on_track")

        agent = Agent(
            role="测试",
            goal="测试",
            backstory="测试",
            tools=[],
            llm=MockLLMAdapter(),
            brain_strategy=StubBrain(),
        )
        result = asyncio.run(agent.run("anything"))
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, "stub")

    def test_agent_with_unknown_strategy_raises(self):
        from lca.layer4_app.api import Agent

        with self.assertRaises(ValueError) as ctx:
            Agent(
                role="测试",
                goal="测试",
                backstory="测试",
                tools=[],
                llm=MockLLMAdapter(),
                brain_strategy="nonexistent",
            )
        self.assertIn("nonexistent", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
