"""Agent 传输层骨架 —— 内部传输实现。"""

from __future__ import annotations

import uuid
from typing import Any

from lca.contracts.decision import Observation
from lca.contracts.protocols import AgentTransport


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class InternalTransport(AgentTransport):
    """进程内 Agent 间通信传输实现。"""

    def __init__(self) -> None:
        self._results: dict[str, Observation] = {}

    async def send_task(self, agent_card: Any, subtask: str, context_refs: list[str]) -> str:
        task_id = _new_id("task")
        return task_id

    async def poll_status(self, task_id: str) -> str:
        if task_id in self._results:
            return "completed"
        return "working"

    async def receive_result(self, task_id: str) -> Observation:
        return self._results.get(task_id, Observation(
            observation_id=_new_id("obs"), success=False, payload=None, error="task not found"
        ))
