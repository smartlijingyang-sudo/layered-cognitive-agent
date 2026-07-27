"""SimpleBody.delegate 分支单元测试 —— 验证 Body 通过 TransportRegistry 按协议路由委派任务。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.decision import (
    DelegationSpec,
    Observation,
    StructuredDecision,
    ToolCall,
)
from lca.contracts.result import ToolExecutionError
from lca.contracts.state import Budget, TypedState
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.transport_registry import (
    TransportNotFoundError,
    TransportRegistry,
    UnimplementedTransport,
)
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry


def _make_registry(transport: InternalTransport) -> TransportRegistry:
    registry = TransportRegistry()
    registry.register(transport)
    return registry


def _make_state() -> TypedState:
    return TypedState(trace_id="test-trace", task="test", budget=Budget())


def _make_decision(
    action_type: str = "delegate",
    delegate_to: DelegationSpec | None = None,
    tool_calls: list[ToolCall] | None = None,
) -> StructuredDecision:
    return StructuredDecision(
        decision_id="dec-1",
        action_type=action_type,  # type: ignore[arg-type]
        rationale="test",
        confidence=1.0,
        tool_calls=tool_calls or [],
        delegate_to=delegate_to,
    )


async def _echo_handler(subtask: str) -> Observation:
    return Observation(observation_id="echo", success=True, payload=f"delegated: {subtask}")


async def _slow_handler(subtask: str) -> Observation:
    await asyncio.sleep(0.2)
    return Observation(observation_id="slow", success=True, payload="slow done")


async def _failing_handler(subtask: str) -> Observation:
    raise RuntimeError("agent exploded")


class TestDelegateHappyPath(unittest.IsolatedAsyncioTestCase):
    """delegate 分支：send_task → poll → receive_result 正常返回。"""

    async def test_delegate_by_agent_id(self) -> None:
        transport = InternalTransport()
        transport.register_agent("researcher", _echo_handler)
        body = SimpleBody(
            SimpleToolRegistry(), _noop_executor(), transport_registry=_make_registry(transport)
        )

        spec = DelegationSpec(subtask="分析数据", target_agent_id="researcher")
        decision = _make_decision(delegate_to=spec)

        obs = await body.act(decision, _make_state())

        self.assertTrue(obs.success)
        self.assertEqual(obs.payload, "delegated: 分析数据")
        self.assertIn("task_id", obs.extra)

    async def test_delegate_by_role_fallback(self) -> None:
        transport = InternalTransport()
        transport.register_agent("analyst", _echo_handler)
        body = SimpleBody(
            SimpleToolRegistry(), _noop_executor(), transport_registry=_make_registry(transport)
        )

        spec = DelegationSpec(subtask="分析", target_role="analyst")
        decision = _make_decision(delegate_to=spec)

        obs = await body.act(decision, _make_state())
        self.assertTrue(obs.success)
        self.assertEqual(obs.payload, "delegated: 分析")

    async def test_delegate_by_string_key(self) -> None:
        """target_agent_card 为字符串时直接作为 directory key。"""
        transport = InternalTransport()
        transport.register_agent("worker-key", _echo_handler)
        body = SimpleBody(
            SimpleToolRegistry(), _noop_executor(), transport_registry=_make_registry(transport)
        )

        spec = DelegationSpec(subtask="执行", target_agent_card="worker-key")
        decision = _make_decision(delegate_to=spec)

        obs = await body.act(decision, _make_state())
        self.assertTrue(obs.success)

    async def test_delegate_passes_context_refs(self) -> None:
        async def capture_handler(subtask: str) -> Observation:
            return Observation(observation_id="cap", success=True, payload=subtask)

        transport = InternalTransport()
        transport.register_agent("worker", capture_handler)
        body = SimpleBody(
            SimpleToolRegistry(), _noop_executor(), transport_registry=_make_registry(transport)
        )

        refs = ["ctx://doc/1", "ctx://doc/2"]
        spec = DelegationSpec(subtask="处理", target_agent_id="worker", context_refs=refs)
        decision = _make_decision(delegate_to=spec)

        obs = await body.act(decision, _make_state())
        self.assertTrue(obs.success)


class TestDelegatePolling(unittest.IsolatedAsyncioTestCase):
    """验证轮询语义：handler 异步执行期间 poll 返回 working，完成后拿到结果。"""

    async def test_delegate_waits_for_slow_handler(self) -> None:
        transport = InternalTransport()
        transport.register_agent("slow", _slow_handler)
        body = SimpleBody(
            SimpleToolRegistry(), _noop_executor(), transport_registry=_make_registry(transport)
        )

        spec = DelegationSpec(subtask="慢任务", target_agent_id="slow")
        decision = _make_decision(delegate_to=spec)

        obs = await body.act(decision, _make_state())
        self.assertTrue(obs.success)
        self.assertEqual(obs.payload, "slow done")


class TestDelegateErrors(unittest.IsolatedAsyncioTestCase):
    """delegate 分支的错误路径。"""

    async def test_no_transport_raises_clear_error(self) -> None:
        body = SimpleBody(SimpleToolRegistry(), _noop_executor())  # 空 registry

        spec = DelegationSpec(subtask="任务", target_agent_id="someone")
        decision = _make_decision(delegate_to=spec)

        with self.assertRaises(TransportNotFoundError) as ctx:
            await body.act(decision, _make_state())
        self.assertIn("internal", str(ctx.exception))

    async def test_missing_delegate_spec_raises_error(self) -> None:
        transport = InternalTransport()
        body = SimpleBody(
            SimpleToolRegistry(), _noop_executor(), transport_registry=_make_registry(transport)
        )

        decision = _make_decision(action_type="delegate", delegate_to=None)

        with self.assertRaises(ToolExecutionError) as ctx:
            await body.act(decision, _make_state())
        self.assertIn("delegate_to", str(ctx.exception))

    async def test_agent_not_found_returns_failed_observation(self) -> None:
        transport = InternalTransport()
        body = SimpleBody(
            SimpleToolRegistry(), _noop_executor(), transport_registry=_make_registry(transport)
        )

        spec = DelegationSpec(subtask="任务", target_agent_id="ghost")
        decision = _make_decision(delegate_to=spec)

        obs = await body.act(decision, _make_state())
        self.assertFalse(obs.success)
        self.assertIn("not found", obs.error)  # type: ignore[arg-type]

    async def test_handler_exception_returns_failed_observation(self) -> None:
        transport = InternalTransport()
        transport.register_agent("broken", _failing_handler)
        body = SimpleBody(
            SimpleToolRegistry(), _noop_executor(), transport_registry=_make_registry(transport)
        )

        spec = DelegationSpec(subtask="触发异常", target_agent_id="broken")
        decision = _make_decision(delegate_to=spec)

        obs = await body.act(decision, _make_state())
        self.assertFalse(obs.success)
        self.assertIn("exploded", obs.error)  # type: ignore[arg-type]


class TestDelegateDoesNotAffectOtherBranches(unittest.IsolatedAsyncioTestCase):
    """确保新增 delegate 分支不影响 respond / use_tool 原有行为。"""

    async def test_respond_still_works(self) -> None:
        body = SimpleBody(SimpleToolRegistry(), _noop_executor())
        decision = _make_decision(action_type="respond")
        decision.response_text = "hello"

        obs = await body.act(decision, _make_state())
        self.assertTrue(obs.success)
        self.assertEqual(obs.payload, "hello")

    async def test_unknown_action_still_raises(self) -> None:
        body = SimpleBody(SimpleToolRegistry(), _noop_executor())
        decision = _make_decision(action_type="ask_human")  # type: ignore[arg-type]

        with self.assertRaises(ToolExecutionError):
            await body.act(decision, _make_state())


class TestProtocolRouting(unittest.IsolatedAsyncioTestCase):
    """验证 _handle_delegate 按 spec.protocol 路由到不同 transport。"""

    async def test_unimplemented_protocol_raises_not_implemented(self) -> None:
        registry = TransportRegistry()
        registry.register(InternalTransport())
        registry.register(UnimplementedTransport("a2a"))
        body = SimpleBody(SimpleToolRegistry(), _noop_executor(), transport_registry=registry)

        spec = DelegationSpec(subtask="跨进程任务", target_agent_id="remote", protocol="a2a")
        decision = _make_decision(delegate_to=spec)

        with self.assertRaises(NotImplementedError) as ctx:
            await body.act(decision, _make_state())
        self.assertIn("a2a", str(ctx.exception))

    async def test_protocol_routes_to_correct_transport(self) -> None:
        internal = InternalTransport()
        internal.register_agent("worker", _echo_handler)
        registry = TransportRegistry()
        registry.register(internal)
        body = SimpleBody(SimpleToolRegistry(), _noop_executor(), transport_registry=registry)

        spec = DelegationSpec(subtask="内部任务", target_agent_id="worker", protocol="internal")
        decision = _make_decision(delegate_to=spec)

        obs = await body.act(decision, _make_state())
        self.assertTrue(obs.success)
        self.assertEqual(obs.payload, "delegated: 内部任务")

    async def test_unknown_protocol_raises_transport_not_found(self) -> None:
        registry = TransportRegistry()
        body = SimpleBody(SimpleToolRegistry(), _noop_executor(), transport_registry=registry)

        spec = DelegationSpec(subtask="任务", target_agent_id="x", protocol="internal")
        decision = _make_decision(delegate_to=spec)

        with self.assertRaises(TransportNotFoundError):
            await body.act(decision, _make_state())


class TestBackwardCompatTransport(unittest.IsolatedAsyncioTestCase):
    """验证旧的 transport= 参数仍然可用。"""

    async def test_transport_kwarg_still_works(self) -> None:
        transport = InternalTransport()
        transport.register_agent("worker", _echo_handler)
        body = SimpleBody(SimpleToolRegistry(), _noop_executor(), transport=transport)

        spec = DelegationSpec(subtask="测试", target_agent_id="worker")
        decision = _make_decision(delegate_to=spec)

        obs = await body.act(decision, _make_state())
        self.assertTrue(obs.success)


def _noop_executor():
    """返回一个最小化的 SafeExecutorProtocol 桩件，delegate 分支不会用到它。"""
    from unittest.mock import AsyncMock

    return AsyncMock()


if __name__ == "__main__":
    unittest.main()
