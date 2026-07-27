"""内存状态存储实现。"""

from __future__ import annotations

from lca.contracts.protocols import StateStore
from lca.contracts.state import TypedState


class InMemoryStateStore(StateStore):
    """基于字典的内存状态存储。"""

    def __init__(self) -> None:
        self._store: dict[str, TypedState] = {}

    async def save(self, state: TypedState) -> str:
        ref = f"mem://{state.trace_id}/{state.step}"
        self._store[ref] = state
        return ref

    async def load(self, state_ref: str) -> TypedState:
        return self._store[state_ref]
