"""InternalTransport 单元测试 —— 验证 send_task → poll_status → receive_result 完整链路。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.decision import Observation
from lca.contracts.lifecycle import AgentCard
from lca.layer0_infra.transport.agent_transport import InternalTransport


async def _echo_handler(subtask: str) -> Observation:
    return Observation(
        observation_id="echo",
        success=True,
        payload=f"echo: {subtask}",
    )


async def _slow_handler(subtask: str) -> Observation:
    await asyncio.sleep(0.05)
    return Observation(
        observation_id="slow",
        success=True,
        payload="done",
    )


async def _failing_handler(subtask: str) -> Observation:
    raise RuntimeError("boom")


class TestInternalTransportHappyPath(unittest.IsolatedAsyncioTestCase):
    """send_task → poll_status → receive_result 三步拿到正确结果。"""

    async def test_string_key_round_trip(self) -> None:
        transport = InternalTransport()
        transport.register_agent("researcher", _echo_handler)

        task_id = await transport.send_task("researcher", "分析数据", [])

        # 等待后台任务完成
        await transport._tasks[task_id]

        status = await transport.poll_status(task_id)
        self.assertEqual(status, "completed")

        result = await transport.receive_result(task_id)
        self.assertTrue(result.success)
        self.assertEqual(result.payload, "echo: 分析数据")

    async def test_agent_card_by_agent_id(self) -> None:
        transport = InternalTransport()
        transport.register_agent("agent-007", _echo_handler)

        card = AgentCard(agent_id="agent-007", role="spy", capabilities=["espionage"])
        task_id = await transport.send_task(card, "秘密任务", [])
        await transport._tasks[task_id]

        result = await transport.receive_result(task_id)
        self.assertTrue(result.success)
        self.assertEqual(result.payload, "echo: 秘密任务")

    async def test_agent_card_fallback_to_role(self) -> None:
        transport = InternalTransport()
        transport.register_agent("analyst", _echo_handler)

        card = AgentCard(agent_id="unknown-id", role="analyst", capabilities=[])
        task_id = await transport.send_task(card, "分析", [])
        await transport._tasks[task_id]

        result = await transport.receive_result(task_id)
        self.assertTrue(result.success)

    async def test_constructor_with_directory(self) -> None:
        transport = InternalTransport(agent_directory={"worker": _echo_handler})

        task_id = await transport.send_task("worker", "hello", [])
        await transport._tasks[task_id]

        result = await transport.receive_result(task_id)
        self.assertTrue(result.success)
        self.assertEqual(result.payload, "echo: hello")


class TestInternalTransportAsync(unittest.IsolatedAsyncioTestCase):
    """验证异步调度语义：send_task 立即返回，handler 异步执行。"""

    async def test_poll_working_before_completion(self) -> None:
        transport = InternalTransport()
        transport.register_agent("slow", _slow_handler)

        task_id = await transport.send_task("slow", "耗时任务", [])

        # 不给 event loop 机会执行后台任务
        status = await transport.poll_status(task_id)
        self.assertEqual(status, "working")

        # 等待后台任务完成
        await asyncio.sleep(0.1)
        status = await transport.poll_status(task_id)
        self.assertEqual(status, "completed")

    async def test_concurrent_tasks(self) -> None:
        transport = InternalTransport()
        transport.register_agent("echo", _echo_handler)

        ids = await asyncio.gather(
            transport.send_task("echo", "任务A", []),
            transport.send_task("echo", "任务B", []),
            transport.send_task("echo", "任务C", []),
        )
        await asyncio.gather(*(transport._tasks[tid] for tid in ids))

        results = [await transport.receive_result(tid) for tid in ids]
        payloads = sorted(r.payload for r in results)
        self.assertEqual(payloads, ["echo: 任务A", "echo: 任务B", "echo: 任务C"])


class TestInternalTransportErrors(unittest.IsolatedAsyncioTestCase):
    """错误处理路径。"""

    async def test_agent_not_found(self) -> None:
        transport = InternalTransport()

        task_id = await transport.send_task("nonexistent", "任务", [])
        status = await transport.poll_status(task_id)
        self.assertEqual(status, "failed")

        result = await transport.receive_result(task_id)
        self.assertFalse(result.success)
        self.assertIn("not found", result.error)

    async def test_handler_exception(self) -> None:
        transport = InternalTransport()
        transport.register_agent("broken", _failing_handler)

        task_id = await transport.send_task("broken", "触发异常", [])
        await transport._tasks[task_id]

        result = await transport.receive_result(task_id)
        self.assertFalse(result.success)
        self.assertIn("boom", result.error)

    async def test_receive_unknown_task(self) -> None:
        transport = InternalTransport()
        result = await transport.receive_result("task_does_not_exist")
        self.assertFalse(result.success)
        self.assertIn("not found", result.error)


if __name__ == "__main__":
    unittest.main()
