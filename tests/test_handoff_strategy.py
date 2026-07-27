"""HandoffStrategy + handoff action_type 测试 —— 控制权移交、短路退出、budget 正确关闭。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lca.layer4_app.defaults  # noqa: F401 — 触发 register_defaults()
from lca.contracts.decision import DelegationSpec, StructuredDecision
from lca.contracts.protocols import OrchestrationContext
from lca.contracts.result import Result
from lca.contracts.state import Budget
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.orchestration_strategies import HandoffStrategy


def _make_result(trace_id: str, output: str, status: str = "completed") -> Result:
    return Result(
        trace_id=trace_id,
        status=status,  # type: ignore[arg-type]
        final_state_ref=f"mem://{trace_id}/0",
        total_steps=1,
        budget_used=Budget(),
        output=output,
    )


def _make_agent(role: str, output: str, status: str = "completed") -> MagicMock:
    agent = MagicMock()
    agent.role_profile = MagicMock()
    agent.role_profile.role = role

    async def _execute(task: str) -> Result:
        return _make_result(f"trace-{role}", output, status=status)

    agent.execute = AsyncMock(side_effect=_execute)
    return agent


class TestHandoffStrategyBasic(unittest.IsolatedAsyncioTestCase):
    """HandoffStrategy 基本功能。"""

    async def test_first_agent_completes_short_circuits(self) -> None:
        """第一个 Agent 完成即返回，后续 Agent 不执行。"""
        agent_a = _make_agent("triage", "routed")
        agent_b = _make_agent("expert", "should not run")

        strategy = HandoffStrategy()
        context = OrchestrationContext(members=[agent_a, agent_b])

        result = await strategy.run(context, "customer question")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, "routed")
        agent_a.execute.assert_awaited_once()
        agent_b.execute.assert_not_awaited()

    async def test_fallback_to_next_agent_on_failure(self) -> None:
        """第一个 Agent 失败时，继续尝试下一个。"""
        agent_a = _make_agent("triage", "", status="failed")
        agent_b = _make_agent("expert", "handled by expert")

        strategy = HandoffStrategy()
        context = OrchestrationContext(members=[agent_a, agent_b])

        result = await strategy.run(context, "complex question")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, "handled by expert")

    async def test_all_agents_fail(self) -> None:
        """所有 Agent 都失败时返回最后一个失败结果。"""
        agent_a = _make_agent("a", "", status="failed")
        agent_b = _make_agent("b", "", status="failed")

        strategy = HandoffStrategy()
        context = OrchestrationContext(members=[agent_a, agent_b])

        result = await strategy.run(context, "task")

        self.assertEqual(result.status, "failed")

    async def test_empty_members_returns_failed(self) -> None:
        strategy = HandoffStrategy()
        context = OrchestrationContext(members=[])

        result = await strategy.run(context, "task")

        self.assertEqual(result.status, "failed")
        self.assertIn("No members", result.error)  # type: ignore[arg-type]

    async def test_single_member(self) -> None:
        agent = _make_agent("solo", "solo result")
        strategy = HandoffStrategy()
        context = OrchestrationContext(members=[agent])

        result = await strategy.run(context, "task")

        self.assertEqual(result.output, "solo result")


class TestHandoffActionType(unittest.TestCase):
    """handoff action_type 在 StructuredDecision 中可用。"""

    def test_handoff_in_action_type_literal(self) -> None:
        import typing

        hints = typing.get_type_hints(StructuredDecision)
        action_type = hints["action_type"]
        valid_values = set(typing.get_args(action_type))
        self.assertIn("handoff", valid_values)


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

        body = SimpleBody(tool_registry, safe_executor, transport_registry=transport_registry)

        decision = StructuredDecision(
            decision_id="d1",
            action_type="handoff",
            rationale="route to expert",
            confidence=0.9,
            delegate_to=DelegationSpec(subtask="help me", target_role="expert"),
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
        body = SimpleBody(tool_registry, safe_executor)

        decision = StructuredDecision(
            decision_id="d1",
            action_type="handoff",
            rationale="route",
            confidence=0.5,
        )
        state = MagicMock()

        from lca.contracts.result import ToolExecutionError

        with self.assertRaises(ToolExecutionError):
            await body.act(decision, state)


class TestHandoffRuntimeStop(unittest.IsolatedAsyncioTestCase):
    """CognitiveRuntime 在 handoff 时应停止循环。"""

    async def test_runtime_stops_on_handoff(self) -> None:
        """handoff action 应触发 _should_stop 返回 True。"""
        from lca.layer2_runtime.runtime_loop import CognitiveRuntime

        brain = MagicMock()
        body = MagicMock()
        memory = MagicMock()
        hooks = MagicMock()
        event_bus = MagicMock()
        state_store = MagicMock()

        hooks.trigger = AsyncMock()
        memory.perceive_and_retrieve = AsyncMock(side_effect=lambda s: s)
        memory.update_multi_level = AsyncMock()

        decision = StructuredDecision(
            decision_id="d1",
            action_type="handoff",
            rationale="handoff to expert",
            confidence=0.9,
            delegate_to=DelegationSpec(subtask="help", target_role="expert"),
        )
        brain.think = AsyncMock(return_value=decision)
        brain.reflect = AsyncMock(
            return_value=MagicMock(verdict="on_track"),
        )

        observation = MagicMock()
        observation.success = True
        body.act = AsyncMock(return_value=observation)

        state_store.save = AsyncMock(return_value="ref")

        runtime = CognitiveRuntime(brain, body, memory, hooks, event_bus, state_store)
        result = await runtime.run("test task", max_steps=10)

        self.assertEqual(result.status, "completed")
        brain.think.assert_awaited_once()


class TestHandoffRegistration(unittest.TestCase):
    """HandoffStrategy 注册与解析。"""

    def test_handoff_registered(self) -> None:
        registry = get_global_orchestration_registry()
        self.assertTrue(registry.has("handoff"))

    def test_handoff_resolves(self) -> None:
        registry = get_global_orchestration_registry()
        strategy = registry.resolve("handoff")
        self.assertIsInstance(strategy, HandoffStrategy)


if __name__ == "__main__":
    unittest.main()
