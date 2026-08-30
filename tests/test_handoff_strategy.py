from __future__ import annotations

# HandoffStrategy + handoff action_type 测试 —— 控制权移交、短路退出、budget 正确关闭。
import unittest
from unittest.mock import AsyncMock, MagicMock

from lca.contracts.models.core.decision import Decision, DelegationSpec
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import Budget
from lca.contracts.protocols.control_verdict import ControlVerdict, ControlVerdictKind
from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from lca.agent.orchestration_strategies import HandoffStrategy
from lca.plugins.composer.runtime_factory import (
    NullPerceiveHub,
    RuntimeDeps,
    build_fixture_cognitive_runtime,
)
from tests.phase_executors import standard_phase_executors
from tests.support.action_authority import build_test_action_registry, build_test_body
from tests.support.strategy_registry import build_strategy_registry
from tests.support.team_stage import stage_with_invoker

_STRATEGIES = build_strategy_registry()


def _make_result(trace_id: str, output: str, status: TaskStatus = TaskStatus.COMPLETED) -> Result:
    return Result(
        trace_id=trace_id,
        status=status,
        final_state_ref=f"mem://{trace_id}/0",
        total_steps=1,
        budget_used=Budget(),
        output=output,
    )


def _make_agent(role: str, output: str, status: TaskStatus = TaskStatus.COMPLETED) -> MagicMock:
    agent = MagicMock()
    agent.role_profile = MagicMock()
    agent.role_profile.role = role

    async def _execute(task: str) -> Result:
        return _make_result(f"trace-{role}", output, status=status)

    agent.run = AsyncMock(side_effect=_execute)
    return agent


class TestHandoffStrategyBasic(unittest.IsolatedAsyncioTestCase):
    async def test_first_agent_completes_short_circuits(self) -> None:
        """第一个 Agent 完成即返回，后续 Agent 不执行。"""
        agent_a = _make_agent("triage", "routed")
        agent_b = _make_agent("expert", "should not run")

        strategy = HandoffStrategy(stage_with_invoker([agent_a, agent_b]))

        result = await strategy.run("customer question")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, "routed")
        agent_a.run.assert_awaited_once()
        agent_b.run.assert_not_awaited()

    async def test_fallback_to_next_agent_on_failure(self) -> None:
        """第一个 Agent 失败时，继续尝试下一个。"""
        agent_a = _make_agent("triage", "", status=TaskStatus.FAILED)
        agent_b = _make_agent("expert", "handled by expert")

        strategy = HandoffStrategy(stage_with_invoker([agent_a, agent_b]))

        result = await strategy.run("complex question")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, "handled by expert")

    async def test_all_agents_fail(self) -> None:
        """所有 Agent 都失败时返回最后一个失败结果。"""
        agent_a = _make_agent("a", "", status=TaskStatus.FAILED)
        agent_b = _make_agent("b", "", status=TaskStatus.FAILED)

        strategy = HandoffStrategy(stage_with_invoker([agent_a, agent_b]))

        result = await strategy.run("task")

        self.assertEqual(result.status, "failed")

    async def test_empty_members_returns_failed(self) -> None:
        strategy = HandoffStrategy(stage_with_invoker([]))

        result = await strategy.run("task")

        self.assertEqual(result.status, "failed")
        self.assertIn("No members", result.error or "")

    async def test_single_member(self) -> None:
        agent = _make_agent("solo", "solo result")
        strategy = HandoffStrategy(stage_with_invoker([agent]))

        result = await strategy.run("task")

        self.assertEqual(result.output, "solo result")


class TestHandoffActionType(unittest.TestCase):
    """handoff action_type 在 Decision 中可用。"""

    def test_handoff_in_action_registry(self) -> None:
        """handoff 应在 ActionRegistry 的已注册集合中。"""
        from lca.contracts.models.team.role_team import ToolPermissionManifest
        from lca.infrastructure.transport.agent_transport import InternalTransport
        from lca.infrastructure.transport.transport_registry import TransportRegistry
        from lca.cognition.body.safe_executor import SimpleSafeExecutor
        from lca.cognition.body.tool_registry import SimpleToolRegistry

        tool_reg = SimpleToolRegistry()
        safe_exec = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]))
        transport_reg = TransportRegistry()
        transport_reg.register(InternalTransport())
        registry = build_test_action_registry(
            tools=tool_reg,
            safe_executor=safe_exec,
            transport=transport_reg,
        )
        self.assertIn("handoff", registry.allowed_action_types())


class TestHandoffBodyAction(unittest.IsolatedAsyncioTestCase):
    """SimpleBody._handle_handoff 行为。"""

    async def test_handoff_returns_observation(self) -> None:
        """handoff action 应返回成功 Observation 且不轮询。"""
        tool_registry = MagicMock()
        safe_executor = MagicMock()
        transport_registry = MagicMock()

        mock_transport = MagicMock()
        mock_transport.protocol_name = "internal"

        async def _send_task(agent_card, subtask, context_refs):
            return "task_123"

        mock_transport.send_task = AsyncMock(side_effect=_send_task)
        transport_registry.resolve = MagicMock(return_value=mock_transport)

        body = build_test_body(
            tool_registry,
            safe_executor,
            transport=transport_registry,
        )

        decision = Decision(
            decision_id="d1",
            action_type="handoff",
            rationale="route to expert",
            confidence=0.9,
            delegations=[DelegationSpec(subtask="help me", target_role="expert")],
        )
        state = MagicMock()

        observation = await body.act(decision, state)

        self.assertTrue(observation.success)
        self.assertTrue(observation.extra.get("handoff"))
        mock_transport.send_task.assert_awaited_once()

    async def test_handoff_without_delegate_spec_raises(self) -> None:
        """handoff 缺少 delegate_to 应报错。"""
        tool_registry = MagicMock()
        safe_executor = MagicMock()
        body = build_test_body(tool_registry, safe_executor)

        decision = Decision(
            decision_id="d1",
            action_type="handoff",
            rationale="route",
            confidence=0.5,
        )
        state = MagicMock()

        from lca.contracts.models.core.result import ToolExecutionError

        with self.assertRaises(ToolExecutionError):
            await body.act(decision, state)


class _AllowContribution:
    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                plugin_id="test.allow-contribution",
                kind=ControlVerdictKind.ALLOW,
            ),
        )


class TestHandoffRuntimeStop(unittest.IsolatedAsyncioTestCase):
    """CognitiveRuntime 在 handoff 时应停止循环。"""

    async def test_runtime_stops_on_handoff(self) -> None:
        """handoff action 应触发 StopPolicy 返回 should_stop=True。"""
        from lca.plugins.providers.artifact_closure import DefaultArtifactClosure
        from lca.plugins.state.stop_policy import DefaultStopPolicy

        brain = MagicMock()
        body = MagicMock()
        memory = MagicMock()
        hooks = MagicMock()
        state_store = MagicMock()
        plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
        phase_executors: dict[str, object] = dict(standard_phase_executors())
        allow = _AllowContribution()
        for binding in plan.phase_bindings:
            for contribution in binding.contributions:
                phase_executors[contribution.executor] = allow

        hooks.trigger = AsyncMock()
        memory.perceive = AsyncMock(side_effect=lambda s: s)
        memory.update = AsyncMock()

        decision = Decision(
            decision_id="d1",
            action_type="handoff",
            rationale="handoff to expert",
            confidence=0.9,
            delegations=[DelegationSpec(subtask="help", target_role="expert")],
        )
        brain.think = AsyncMock(return_value=decision)
        brain.reflect = AsyncMock(
            return_value=MagicMock(verdict="on_track"),
        )

        observation = MagicMock()
        observation.success = True
        body.act = AsyncMock(return_value=observation)

        state_store.save = AsyncMock(return_value="ref")
        stop_policy = DefaultStopPolicy(DefaultArtifactClosure())
        perceive_hub = NullPerceiveHub()

        runtime = build_fixture_cognitive_runtime(
            RuntimeDeps(
                brain=brain,
                body=body,
                memory=memory,
                hooks=hooks,
                state_store=state_store,
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
            )
        )
        result = await runtime.run("test task", max_steps=10)

        self.assertEqual(result.status, "completed")
        brain.think.assert_awaited_once()


class TestHandoffRegistration(unittest.TestCase):
    """HandoffStrategy 注册与解析。"""

    def test_handoff_registered(self) -> None:
        registry = _STRATEGIES
        self.assertIn("peer_relay", registry)

    def test_handoff_resolves(self) -> None:
        from lca.contracts.models.team.team_coordination import PeerRelay
        from lca.contracts.protocols import TeamAssembly

        registry = _STRATEGIES
        assembly = TeamAssembly(governance=PeerRelay(), stage=stage_with_invoker([]))
        strategy = registry.create("peer_relay", assembly)
        self.assertIsInstance(strategy, HandoffStrategy)


if __name__ == "__main__":
    unittest.main()
