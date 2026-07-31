"""Test-only stub transport whose every method raises NotImplementedError."""

from __future__ import annotations

from lca.contracts.decision import AgentCard, Observation
from lca.contracts.protocols import AgentTransport


class UnimplementedTransport(AgentTransport):
    """Test double: every method raises NotImplementedError.

    Used to simulate the "protocol registered but not implemented" path
    without needing a real A2A/MCP backend.
    """

    def __init__(self, protocol_name: str, tracking_issue: str = "") -> None:
        self.protocol_name = protocol_name
        self._tracking_issue = tracking_issue

    @property
    def _error_message(self) -> str:
        msg = f"协议 {self.protocol_name!r} 的传输实现尚未完成"
        if self._tracking_issue:
            msg += f" (tracked in {self._tracking_issue})"
        return msg

    async def send_task(
        self, agent_card: AgentCard | str, subtask: str, context_refs: list[str]
    ) -> str:
        raise NotImplementedError(self._error_message)

    async def poll_status(self, task_id: str) -> str:
        raise NotImplementedError(self._error_message)

    async def receive_result(self, task_id: str) -> Observation:
        raise NotImplementedError(self._error_message)

    async def wait_result(self, task_id: str, timeout_s: float | None = None) -> Observation:
        raise NotImplementedError(self._error_message)
