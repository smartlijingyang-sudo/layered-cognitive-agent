"""四类记忆的最小实现：内存列表存储 + 简单相关性检索。"""

from __future__ import annotations

import uuid

from lca.contracts.state import TypedState
from lca.contracts.decision import Observation, Reflection
from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols import MemorySystem


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SimpleMemorySystem(MemorySystem):
    """Working / Semantic / Episodic / Procedural 四层记忆。"""

    def __init__(self) -> None:
        self._layers: dict[str, list[MemoryRecord]] = {
            "working": [],
            "semantic": [],
            "episodic": [],
            "procedural": [],
        }

    async def perceive_and_retrieve(self, state: TypedState) -> TypedState:
        records: list[MemoryRecord] = []
        for layer in self._layers.values():
            records.extend(layer)
        state.retrieved_context = records
        return state

    async def update_multi_level(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None:
        if observation.payload is not None and observation.success:
            self._layers["working"] = [MemoryRecord(
                record_id=_new_id("mem"),
                content=f"TOOL_RESULT: {observation.payload}",
                memory_type="working",
                importance=0.9,
                source_trace_id=state.trace_id,
            )]
        self._layers["episodic"].append(MemoryRecord(
            record_id=_new_id("mem"),
            content=f"step={state.step} success={observation.success} verdict={reflection.verdict}",
            memory_type="episodic",
            importance=0.5,
            source_trace_id=state.trace_id,
        ))
        await self.compress()

    async def compress(self) -> None:
        max_episodic = 50
        if len(self._layers["episodic"]) > max_episodic:
            self._layers["episodic"] = self._layers["episodic"][-max_episodic:]
