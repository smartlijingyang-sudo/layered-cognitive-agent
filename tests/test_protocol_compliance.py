"""验证所有实现类显式满足对应 Protocol 的 isinstance 断言。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

from cordis import Context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.protocols import (
    AgentTransport,
    AgentUnit,
    Body,
    Brain,
    Critic,
    EventBus,
    HookRegistry,
    LLMAdapter,
    MemorySystem,
    Reasoner,
    Runtime,
    SafeExecutor,
    StateStore,
    TeamUnit,
    Tool,
    ToolRegistry,
)
from lca.harness.observability import make_minimal_bound
from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter
from lca.infrastructure.llm_adapter.openai_compat import OpenAICompatAdapter
from lca.infrastructure.state_store.in_memory_store import InMemoryStateStore
from lca.infrastructure.tools.calculator import build_tools as build_calculator_tools
from lca.infrastructure.tools.weather import build_tools as build_weather_tools
from lca.infrastructure.transport.agent_transport import InternalTransport
from lca.infrastructure.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.action_registry import ActionRegistry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry

# L1
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import PromptReasoner
from lca.layer1_cognitive.event_bus import CordisEventBus
from lca.layer1_cognitive.hook_registry import CordisHookRegistry
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem

# L2
from lca.layer2_runtime.reducer import DefaultReducer

# L3
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.plugins.composer.runtime_factory import (
    NullPerceiveHub,
    RuntimeDeps,
    build_fixture_cognitive_runtime,
)
from lca.plugins.providers.artifact_closure import DefaultArtifactClosure
from lca.plugins.providers.decision_classifier import DefaultDecisionClassifier
from lca.plugins.state.stop_policy import DefaultStopPolicy
from tests.support.unimplemented_transport import UnimplementedTransport


class TestL0ProtocolCompliance(unittest.TestCase):
    """L0 基础设施层：所有实现类满足对应 Protocol。"""

    def test_mock_llm_is_llm_adapter(self):
        self.assertIsInstance(MockLLMAdapter(), LLMAdapter)

    def test_openai_compat_is_llm_adapter(self):
        self.assertIsInstance(OpenAICompatAdapter.__new__(OpenAICompatAdapter), LLMAdapter)

    def test_calculator_is_tool(self):
        self.assertIsInstance(build_calculator_tools()[0], Tool)

    def test_weather_is_tool(self):
        self.assertIsInstance(build_weather_tools()[0], Tool)

    def test_bound_observability_satisfies_backend(self):
        """BoundObservability satisfies ObservabilityBackend protocol structurally."""
        from lca.contracts.protocols import ObservabilityBackend
        from lca.infrastructure.observability import BoundObservability

        self.assertIsInstance(BoundObservability(), ObservabilityBackend)

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
        from lca.plugins.composer.team_transport import build_default_transport_registry

        registry = build_default_transport_registry()
        for protocol in ("internal", "a2a", "mcp"):
            transport = registry.resolve(protocol)
            self.assertIsNotNone(transport, f"protocol {protocol!r} 未注册")


class TestL1ProtocolCompliance(unittest.TestCase):
    """L1 认知层：所有实现类满足对应 Protocol。"""

    def _build_brain_deps(self):
        """构建 ModularBrain 所需的依赖。"""
        from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest

        llm = MockLLMAdapter()
        rp = RoleProfile(
            role="t",
            goal="t",
            backstory="t",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        reasoner = PromptReasoner(llm, rp, "(无)", templates={"react_prompt": "test"})
        return reasoner

    def test_modular_brain_is_brain(self):
        reasoner = self._build_brain_deps()
        brain = ModularBrain(
            reasoner=reasoner,
            reducer=DefaultReducer(),
            classifier=DefaultDecisionClassifier(),
            critic=SimpleCritic(),
        )
        self.assertIsInstance(brain, Brain)

    def test_simple_reasoner(self):
        reasoner = self._build_brain_deps()
        self.assertIsInstance(reasoner, Reasoner)

    def test_simple_critic(self):
        self.assertIsInstance(SimpleCritic(), Critic)

    def test_simple_body(self):
        tool_reg = SimpleToolRegistry()
        from lca.contracts.models.team.role_team import ToolPermissionManifest

        executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]))
        body = SimpleBody(tool_reg, executor, TransportRegistry(), ActionRegistry())
        self.assertIsInstance(body, Body)

    def test_simple_tool_registry(self):
        self.assertIsInstance(SimpleToolRegistry(), ToolRegistry)

    def test_simple_safe_executor(self):
        from lca.contracts.models.team.role_team import ToolPermissionManifest

        executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]))
        self.assertIsInstance(executor, SafeExecutor)

    def test_simple_memory_system(self):
        self.assertIsInstance(SimpleMemorySystem(), MemorySystem)

    def test_cordis_event_bus(self):
        self.assertIsInstance(CordisEventBus(object()), EventBus)

    def test_cordis_hook_registry(self):
        self.assertIsInstance(CordisHookRegistry(Context()), HookRegistry)


class TestL2ProtocolCompliance(unittest.TestCase):
    """L2 运行时层。"""

    def test_cognitive_runtime_is_runtime(self):
        from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest

        llm = MockLLMAdapter()
        rp = RoleProfile(
            role="t",
            goal="t",
            backstory="t",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        reasoner = PromptReasoner(llm, rp, "(无)", templates={"react_prompt": "test"})
        brain = ModularBrain(
            reasoner=reasoner,
            reducer=DefaultReducer(),
            classifier=DefaultDecisionClassifier(),
            critic=SimpleCritic(),
        )
        body = SimpleBody(
            SimpleToolRegistry(),
            SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[])),
            TransportRegistry(),
            ActionRegistry(),
        )
        memory = SimpleMemorySystem()
        perceive_hub = NullPerceiveHub()
        stop_policy = DefaultStopPolicy(DefaultArtifactClosure())
        runtime = build_fixture_cognitive_runtime(
            RuntimeDeps(
                brain=brain,
                body=body,
                memory=memory,
                hooks=CordisHookRegistry(Context()),
                state_store=InMemoryStateStore(),
                perceive_hub=perceive_hub,
                phase_capabilities={
                    "brain": brain,
                    "body": body,
                    "memory": memory,
                    "perceive_hub": perceive_hub,
                    "stop_policy": stop_policy,
                },
                stop_policy=stop_policy,
            )
        )
        self.assertIsInstance(runtime, Runtime)


class TestL3ProtocolCompliance(unittest.TestCase):
    """L3 Agent 层。"""

    def _build_agent(self):
        from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest

        llm = MockLLMAdapter()
        rp = RoleProfile(
            role="t",
            goal="t",
            backstory="t",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        reasoner = PromptReasoner(llm, rp, "(无)", templates={"react_prompt": "test"})
        brain = ModularBrain(
            reasoner=reasoner,
            reducer=DefaultReducer(),
            classifier=DefaultDecisionClassifier(),
            critic=SimpleCritic(),
        )
        body = SimpleBody(
            SimpleToolRegistry(),
            SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[])),
            TransportRegistry(),
            ActionRegistry(),
        )
        memory = SimpleMemorySystem()
        perceive_hub = NullPerceiveHub()
        stop_policy = DefaultStopPolicy(DefaultArtifactClosure())
        runtime = build_fixture_cognitive_runtime(
            RuntimeDeps(
                brain=brain,
                body=body,
                memory=memory,
                hooks=CordisHookRegistry(Context()),
                state_store=InMemoryStateStore(),
                perceive_hub=perceive_hub,
                phase_capabilities={
                    "brain": brain,
                    "body": body,
                    "memory": memory,
                    "perceive_hub": perceive_hub,
                    "stop_policy": stop_policy,
                },
                stop_policy=stop_policy,
            )
        )
        return CognitiveAgent(runtime, rp, make_minimal_bound()), rp, runtime

    def test_agent_is_agent_runtime(self):
        agent, _, _ = self._build_agent()
        self.assertIsInstance(agent, AgentUnit)

    def test_supervisor_is_agent_runtime(self):
        _, rp, runtime = self._build_agent()
        sup = CognitiveAgent(
            runtime, rp, make_minimal_bound(), max_steps=20, max_wall_clock_seconds=300
        )
        self.assertIsInstance(sup, AgentUnit)

    def test_team_handle_is_team_runtime(self):
        from lca.contracts.models.team.team_coordination import (
            Pipeline,
        )
        from lca.layer4_app.spawn import spawn_team
        from tests.support.agent_specs import make_spec

        agent, _rp, _runtime = self._build_agent()
        handle = spawn_team(
            members=[make_spec(agent.role_profile.role, MockLLMAdapter())],
            coordination=Pipeline(),
        )
        self.assertIsInstance(handle, TeamUnit)


class TestBrainFactoryRegistryIntegration(unittest.TestCase):
    """验证 Brain 工厂注册表动态选择 Brain 实现。"""

    def test_default_brain_registered(self):
        import asyncio

        from lca.harness.profile.boot import boot_profile

        ctx = asyncio.run(boot_profile("profiles/test-minimal.yaml"))
        self.assertIn("default", ctx.inject("brains"))

    def test_agent_with_string_brain(self):
        from lca.layer4_app.api import Agent

        agent = Agent(
            role="测试",
            goal="测试",
            backstory="测试",
            tools=build_calculator_tools(),
            llm=MockLLMAdapter(),
            brain="default",
        )
        result = asyncio.run(agent.run("1 + 2"))
        self.assertEqual(result.status, "completed")

    def test_agent_with_custom_brain(self):
        from lca.contracts.atoms.ids import new_id
        from lca.contracts.models.core.decision import Decision, Reflection
        from lca.contracts.models.core.state import AgentState
        from lca.layer4_app.api import Agent

        class StubBrain(Brain):
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

        agent = Agent(
            role="测试",
            goal="测试",
            backstory="测试",
            tools=[],
            llm=MockLLMAdapter(),
            brain=StubBrain(),
        )
        result = asyncio.run(agent.run("anything"))
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, "stub")

    def test_agent_with_unknown_brain_raises(self):
        from lca.layer4_app.api import Agent

        with self.assertRaises(ValueError) as ctx:
            Agent(
                role="测试",
                goal="测试",
                backstory="测试",
                tools=[],
                llm=MockLLMAdapter(),
                brain="nonexistent",
            )
        self.assertIn("nonexistent", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
