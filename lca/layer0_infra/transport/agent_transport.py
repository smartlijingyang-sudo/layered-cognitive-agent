"""Agent 传输层 —— 进程内传输实现（对齐 A2A 异步任务模型）。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.decision import Observation
from lca.contracts.ids import new_id
from lca.contracts.protocols import AgentTransport

AgentHandler = Callable[[str], Awaitable[Observation]]


def _fail_observation(error: str) -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error=error,
    )


class InternalTransport(AgentTransport):
    """进程内 Agent 间通信传输实现。

    维护 ``agent_directory``（key → async handler），``send_task`` 通过
    ``asyncio.create_task`` 异步调度 handler。调用方优先用 ``wait_result``
    await Future；``poll_status`` / ``receive_result`` 保留以兼容统一协议。
    """

    protocol_name: str = "internal"

    def __init__(
        self,
        agent_directory: dict[str, AgentHandler] | None = None,
    ) -> None:
        self._directory: dict[str, AgentHandler] = dict(agent_directory or {})
        self._results: dict[str, Observation] = {}
        self._statuses: dict[str, str] = {}
        self._futures: dict[str, asyncio.Future[Observation]] = {}
        self._bg_tasks: dict[str, asyncio.Task[None]] = {}

    def register_agent(self, key: str, handler: AgentHandler) -> None:
        """将一个 async handler 注册到 directory，key 通常为 agent_id 或 role。"""
        self._directory[key] = handler

    def _resolve_handler(self, agent_card: Any) -> AgentHandler | None:
        if isinstance(agent_card, str):
            return self._directory.get(agent_card)
        if hasattr(agent_card, "agent_id"):
            handler = self._directory.get(agent_card.agent_id)
            if handler is not None:
                return handler
        if hasattr(agent_card, "role"):
            return self._directory.get(agent_card.role)
        return None

    async def send_task(self, agent_card: Any, subtask: str, context_refs: list[str]) -> str:
        task_id = new_id("task")
        handler = self._resolve_handler(agent_card)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Observation] = loop.create_future()
        self._futures[task_id] = fut

        if handler is None:
            obs = _fail_observation("agent not found in directory")
            self._statuses[task_id] = "failed"
            self._results[task_id] = obs
            fut.set_result(obs)
            return task_id

        async def _run() -> None:
            try:
                obs = await handler(subtask)
            except Exception as exc:
                obs = _fail_observation(str(exc))
            self._results[task_id] = obs
            self._statuses[task_id] = "completed" if obs.success else "failed"
            if not fut.done():
                fut.set_result(obs)

        self._statuses[task_id] = "working"
        self._bg_tasks[task_id] = asyncio.create_task(_run(), name=f"transport-{task_id}")
        return task_id

    async def poll_status(self, task_id: str) -> str:
        return self._statuses.get(task_id, "working")

    async def receive_result(self, task_id: str) -> Observation:
        if task_id in self._results:
            return self._results[task_id]
        fut = self._futures.get(task_id)
        if fut is not None and fut.done():
            return fut.result()
        return _fail_observation("task not found")

    async def wait_result(self, task_id: str, timeout_s: float | None = None) -> Observation:
        fut = self._futures.get(task_id)
        if fut is None:
            if task_id in self._results:
                return self._results[task_id]
            return _fail_observation("task not found")
        if timeout_s is None:
            return await fut
        return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout_s)
