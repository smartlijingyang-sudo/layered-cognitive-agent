"""Agent 传输层 —— 进程内传输实现（对齐 A2A 异步任务模型）。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.decision import Observation
from lca.contracts.protocols import AgentTransport

AgentHandler = Callable[[str], Awaitable[Observation]]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _fail_obsation(error: str) -> Observation:
    return Observation(
        observation_id=_new_id("obs"),
        success=False,
        payload=None,
        error=error,
    )


class InternalTransport(AgentTransport):
    """进程内 Agent 间通信传输实现。

    维护一个 ``agent_directory``（key → async handler），``send_task`` 通过
    ``asyncio.create_task`` 异步调度 handler，调用方随后用 ``poll_status`` /
    ``receive_result`` 轮询结果 —— 与 Google A2A 的 AgentCard 注册表 + 异步
    任务轮询模型一致。
    """

    def __init__(
        self,
        agent_directory: dict[str, AgentHandler] | None = None,
    ) -> None:
        self._directory: dict[str, AgentHandler] = dict(agent_directory or {})
        self._results: dict[str, Observation] = {}
        self._statuses: dict[str, str] = {}
        self._bg_tasks: dict[str, asyncio.Task[Observation]] = {}

    # -- 注册 -----------------------------------------------------------

    def register_agent(self, key: str, handler: AgentHandler) -> None:
        """将一个 async handler 注册到 directory，key 通常为 agent_id 或 role。"""
        self._directory[key] = handler

    # -- 内部 -----------------------------------------------------------

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

    # -- AgentTransport 协议 --------------------------------------------

    async def send_task(self, agent_card: Any, subtask: str, context_refs: list[str]) -> str:
        task_id = _new_id("task")
        handler = self._resolve_handler(agent_card)

        if handler is None:
            self._statuses[task_id] = "failed"
            self._results[task_id] = _fail_obsation("agent not found in directory")
            return task_id

        async def _run() -> Observation:
            try:
                return await handler(subtask)
            except Exception as exc:
                return _fail_obsation(str(exc))

        self._statuses[task_id] = "working"
        bg = asyncio.create_task(_run(), name=f"transport-{task_id}")
        self._bg_tasks[task_id] = bg

        def _on_done(task: asyncio.Task[Observation]) -> None:
            self._results[task_id] = task.result()
            self._statuses[task_id] = "completed"

        bg.add_done_callback(_on_done)
        return task_id

    async def poll_status(self, task_id: str) -> str:
        return self._statuses.get(task_id, "working")

    async def receive_result(self, task_id: str) -> Observation:
        return self._results.get(task_id, _fail_obsation("task not found"))
