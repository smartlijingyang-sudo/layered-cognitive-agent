"""内存状态存储实现。"""

from __future__ import annotations

from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import StateStore


class InMemoryStateStore(StateStore):
    """基于字典的内存状态存储。"""

    def __init__(self) -> None:
        self._store: dict[str, AgentState] = {}

    async def save(self, state: AgentState) -> str:
        ref = f"mem://{state.trace_id}/{state.step}"
        self._store[ref] = state
        return ref

    async def load(self, state_ref: str) -> AgentState:
        return self._store[state_ref]
