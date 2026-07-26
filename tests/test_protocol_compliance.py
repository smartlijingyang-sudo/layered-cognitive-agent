"""验证所有实现类显式满足对应 Protocol 的 isinstance 断言。"""

from __future__ import annotations

import asyncio
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.protocols import (
    LLMAdapter, ToolProtocol, Reasoner, DecisionParser, Critic,
    TaskDecomposer, StatePredictor, StateEvaluator, ConflictMonitor,
    TaskCoordinator, BrainStrategy, Body, MemorySystem, EventBus,
    PromptManager, ToolRegistryP, SafeExecutorProtocol, StateStore,
    Hook, HookRegistryP, AgentTransport, Observability, Runtime,
    AgentProtocol,
)

# L0
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter
from lca.layer0_infra.llm_adapter.anthropic_llm import AnthropicLLMAdapter
from lca.layer0_infra.tool_protocol.calculator_tool import CalculatorTool
from lca.layer0_infra.tool_protocol.weather_tool import GetWeatherTool
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer0_infra.state_mgmt.in_memory_store import InMemoryStateStore
from lca.layer0_infra.transport.agent_transport import InternalTransport

# L1
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.map_modules.task_decomposer import SimpleTaskDecomposer
from lca.layer1_cognitive.brain.map_modules.state_predictor import SimpleStatePredictor
from lca.layer1_cognitive.brain.map_modules.state_evaluator import SimpleStateEvaluator
from lca.layer1_cognitive.brain.map_modules.conflict_monitor import SimpleConflictMonitor
from lca.layer1_cognitive.brain.map_modules.task_coordinator import SimpleTaskCoordinator
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer1_cognitive.event_bus import SimpleEventBus
from lca.layer1_cognitive.prompt_manager import SimplePromptManager
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook

# L2
from lca.layer2_runtime.runtime_loop import CognitiveRuntime

# L3
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer3_agent.supervisor import Supervisor


class TestL0ProtocolCompliance(unittest.TestCase):
    """L0 基础设施层：所有实现类满足对应 Protocol。"""

    def test_mock_llm_is_llm_adapter(self):
        self.assertIsInstance(MockLLMAdapter(), LLMAdapter)

    def test_openai_compat_is_llm_adapter(self):
        self.assertIsInstance(OpenAICompatAdapter.__new__(OpenAICompatAdapter), LLMAdapter)

    def test_anthropic_is_llm_adapter(self):
        self.assertIsInstance(AnthropicLLMAdapter.__new__(AnthropicLLMAdapter), LLMAdapter)

    def test_calculator_is_tool(self):
        self.assertIsInstance(CalculatorTool(), ToolProtocol)

    def test_weather_is_tool(self):
        self.assertIsInstance(GetWeatherTool(), ToolProtocol)

    def test_console_observability(self):
        self.assertIsInstance(ConsoleObservability(), Observability)

    def test_in_memory_state_store(self):
        self.assertIsInstance(InMemoryStateStore(), StateStore)

    def test_internal_transport(self):
        self.assertIsInstance(InternalTransport(), AgentTransport)


class TestL1ProtocolCompliance(unittest.TestCase):
    """L1 认知层：所有实现类满足对应 Protocol。"""

    def _build_brain_deps(self):
        """构建 ModularBrain 所需的依赖。"""
        from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
        from lca.contracts.state import TypedState, Budget

        llm = MockLLMAdapter()
        pm = SimplePromptManager()
        pm.register_template("react_prompt", "test")
        rp = RoleProfile(role="t", goal="t", backstory="t",
                         tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]))
        reasoner = SimpleReasoner(llm, pm, rp, "(无)")
        return reasoner

    def test_modular_brain_is_brain_strategy(self):
        reasoner = self._build_brain_deps()
        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(),
            critic=SimpleCritic(),
            task_decomposer=SimpleTaskDecomposer(),
            state_predictor=SimpleStatePredictor(),
            state_evaluator=SimpleStateEvaluator(),
            conflict_monitor=SimpleConflictMonitor(),
            task_coordinator=SimpleTaskCoordinator(),
        )
        self.assertIsInstance(brain, BrainStrategy)

    def test_simple_reasoner(self):
        reasoner = self._build_brain_deps()
        self.assertIsInstance(reasoner, Reasoner)

    def test_simple_decision_parser(self):
        self.assertIsInstance(SimpleDecisionParser(), DecisionParser)

    def test_simple_critic(self):
        self.assertIsInstance(SimpleCritic(), Critic)

    def test_simple_task_decomposer(self):
        self.assertIsInstance(SimpleTaskDecomposer(), TaskDecomposer)

    def test_simple_state_predictor(self):
        self.assertIsInstance(SimpleStatePredictor(), StatePredictor)

    def test_simple_state_evaluator(self):
        self.assertIsInstance(SimpleStateEvaluator(), StateEvaluator)

    def test_simple_conflict_monitor(self):
        self.assertIsInstance(SimpleConflictMonitor(), ConflictMonitor)

    def test_simple_task_coordinator(self):
        self.assertIsInstance(SimpleTaskCoordinator(), TaskCoordinator)

    def test_simple_body(self):
        tool_reg = SimpleToolRegistry()
        obs = ConsoleObservability()
        from lca.contracts.role_team import ToolPermissionManifest
        executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]), obs)
        body = SimpleBody(tool_reg, executor)
        self.assertIsInstance(body, Body)

    def test_simple_tool_registry(self):
        self.assertIsInstance(SimpleToolRegistry(), ToolRegistryP)

    def test_simple_safe_executor(self):
        obs = ConsoleObservability()
        from lca.contracts.role_team import ToolPermissionManifest
        executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]), obs)
        self.assertIsInstance(executor, SafeExecutorProtocol)

    def test_simple_memory_system(self):
        self.assertIsInstance(SimpleMemorySystem(), MemorySystem)

    def test_simple_event_bus(self):
        self.assertIsInstance(SimpleEventBus(), EventBus)

    def test_simple_prompt_manager(self):
        self.assertIsInstance(SimplePromptManager(), PromptManager)

    def test_simple_hook_registry(self):
        obs = ConsoleObservability()
        self.assertIsInstance(SimpleHookRegistry(obs), HookRegistryP)

    def test_default_logging_hook_is_hook(self):
        self.assertIsInstance(default_logging_hook, Hook)


class TestL2ProtocolCompliance(unittest.TestCase):
    """L2 运行时层。"""

    def test_cognitive_runtime_is_runtime(self):
        from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
        llm = MockLLMAdapter()
        pm = SimplePromptManager()
        pm.register_template("react_prompt", "test")
        rp = RoleProfile(role="t", goal="t", backstory="t",
                         tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]))
        reasoner = SimpleReasoner(llm, pm, rp, "(无)")
        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(),
            critic=SimpleCritic(),
            task_decomposer=SimpleTaskDecomposer(),
            state_predictor=SimpleStatePredictor(),
            state_evaluator=SimpleStateEvaluator(),
            conflict_monitor=SimpleConflictMonitor(),
            task_coordinator=SimpleTaskCoordinator(),
        )
        obs = ConsoleObservability()
        body = SimpleBody(SimpleToolRegistry(),
                          SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]), obs))
        runtime = CognitiveRuntime(brain, body, SimpleMemorySystem(),
                                   SimpleHookRegistry(obs), SimpleEventBus(),
                                   InMemoryStateStore())
        self.assertIsInstance(runtime, Runtime)


class TestL3ProtocolCompliance(unittest.TestCase):
    """L3 Agent 层。"""

    def _build_base_agent(self):
        from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
        llm = MockLLMAdapter()
        pm = SimplePromptManager()
        pm.register_template("react_prompt", "test")
        rp = RoleProfile(role="t", goal="t", backstory="t",
                         tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]))
        reasoner = SimpleReasoner(llm, pm, rp, "(无)")
        brain = ModularBrain(
            reasoner=reasoner, decision_parser=SimpleDecisionParser(),
            critic=SimpleCritic(), task_decomposer=SimpleTaskDecomposer(),
            state_predictor=SimpleStatePredictor(), state_evaluator=SimpleStateEvaluator(),
            conflict_monitor=SimpleConflictMonitor(), task_coordinator=SimpleTaskCoordinator(),
        )
        obs = ConsoleObservability()
        body = SimpleBody(SimpleToolRegistry(),
                          SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]), obs))
        runtime = CognitiveRuntime(brain, body, SimpleMemorySystem(),
                                   SimpleHookRegistry(obs), SimpleEventBus(),
                                   InMemoryStateStore())
        return BaseAgent(runtime, rp), rp, runtime

    def test_base_agent_is_agent_protocol(self):
        agent, _, _ = self._build_base_agent()
        self.assertIsInstance(agent, AgentProtocol)

    def test_supervisor_is_agent_protocol(self):
        _, rp, runtime = self._build_base_agent()
        sup = Supervisor(runtime, rp)
        self.assertIsInstance(sup, AgentProtocol)


class TestStrategyRegistryIntegration(unittest.TestCase):
    """验证 StrategyRegistry 动态选择 Brain 策略。"""

    def test_default_strategy_registered(self):
        from lca.layer2_runtime.strategy_registry import get_global_strategy_registry
        reg = get_global_strategy_registry()
        self.assertIn("default", reg.list_strategies())

    def test_agent_with_string_strategy(self):
        from lca.layer4_app.api import Agent
        agent = Agent(
            role="测试", goal="测试", backstory="测试",
            tools=[CalculatorTool()], llm=MockLLMAdapter(),
            brain_strategy="default",
        )
        result = asyncio.run(agent.run("1 + 2"))
        self.assertEqual(result.status, "completed")

    def test_agent_with_custom_strategy(self):
        from lca.layer4_app.api import Agent
        from lca.contracts.state import TypedState
        from lca.contracts.decision import Observation, Reflection

        class StubBrain(BrainStrategy):
            async def think(self, state: TypedState):
                return SimpleDecisionParser().parse(
                    '{"action_type":"respond","response_text":"stub","confidence":1.0}', state
                )
            async def reflect(self, state, observation):
                from lca.contracts.decision import Reflection
                return Reflection(reflection_id="r", verdict="on_track")

        agent = Agent(
            role="测试", goal="测试", backstory="测试",
            tools=[], llm=MockLLMAdapter(),
            brain_strategy=StubBrain(),
        )
        result = asyncio.run(agent.run("anything"))
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, "stub")

    def test_agent_with_unknown_strategy_raises(self):
        from lca.layer4_app.api import Agent
        with self.assertRaises(ValueError) as ctx:
            Agent(
                role="测试", goal="测试", backstory="测试",
                tools=[], llm=MockLLMAdapter(),
                brain_strategy="nonexistent",
            )
        self.assertIn("nonexistent", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
