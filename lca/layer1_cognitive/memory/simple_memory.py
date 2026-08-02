"""四类记忆的最小实现：内存列表存储 + 简单相关性检索 + 可选团队共享。"""

from __future__ import annotations

from typing import Any

from lca.contracts.decision import Observation, Reflection
from lca.contracts.enums import MemoryLayer
from lca.contracts.ids import new_id
from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols import MemorySystem, SharedMemoryStore
from lca.contracts.state import AgentState

_DEFAULT_MAX_WORKING = 20
_DEFAULT_MAX_EPISODIC = 50


class SimpleMemorySystem(MemorySystem):
    """Working / Semantic / Episodic / Procedural 四层记忆。

    可选绑定 SharedMemoryStore：对声明共享的层（semantic/procedural），
    读写直接走共享 store，实现跨 Agent 记忆共享；未声明共享的层保持私有。
    """

    def __init__(self) -> None:
        self._shared_store: SharedMemoryStore | None = None
        self._private_layers: dict[MemoryLayer, list[MemoryRecord]] = {
            MemoryLayer.WORKING: [],
            MemoryLayer.SEMANTIC: [],
            MemoryLayer.EPISODIC: [],
            MemoryLayer.PROCEDURAL: [],
        }

    def bind_shared_memory(self, store: SharedMemoryStore) -> None:
        """绑定团队共享记忆存储。共享层的数据读写委托给 store。"""
        self._shared_store = store

    def _get_layer_records(self, layer: MemoryLayer) -> list[MemoryRecord]:
        if self._shared_store is not None and self._shared_store.is_shared(layer):
            return self._shared_store.get_records(layer)
        return self._private_layers[layer]

    def _append_record(self, layer: MemoryLayer, record: MemoryRecord) -> None:
        if self._shared_store is not None and self._shared_store.is_shared(layer):
            self._shared_store.add_record(layer, record)
        else:
            self._private_layers[layer].append(record)

    async def perceive(self, state: AgentState) -> AgentState:
        records: list[MemoryRecord] = []
        for layer_name in self._private_layers:
            records.extend(self._get_layer_records(layer_name))
        state.retrieved_context = records
        return state

    async def update(
        self, state: AgentState, observation: Observation, reflection: Reflection
    ) -> None:
        if observation.payload is not None and observation.success:
            # 追加到 working memory 而非覆盖，确保多步委派历史对 agent 可见
            self._private_layers[MemoryLayer.WORKING].append(
                MemoryRecord(
                    record_id=new_id("mem"),
                    content=f"TOOL_RESULT: {observation.payload}",
                    memory_type=MemoryLayer.WORKING,
                    importance=0.9,
                    source_trace_id=state.trace_id,
                )
            )
            # 防止 working memory 无限增长
            if len(self._private_layers[MemoryLayer.WORKING]) > _DEFAULT_MAX_WORKING:
                self._private_layers[MemoryLayer.WORKING] = self._private_layers[
                    MemoryLayer.WORKING
                ][-_DEFAULT_MAX_WORKING:]
        self._append_record(
            MemoryLayer.EPISODIC,
            MemoryRecord(
                record_id=new_id("mem"),
                content=f"step={state.step} success={observation.success} verdict={reflection.verdict}",
                memory_type=MemoryLayer.EPISODIC,
                importance=0.5,
                source_trace_id=state.trace_id,
            ),
        )
        await self.compress()

    async def compress(self) -> None:
        episodic = self._get_layer_records(MemoryLayer.EPISODIC)
        if len(episodic) > _DEFAULT_MAX_EPISODIC:
            if self._shared_store is not None and self._shared_store.is_shared(
                MemoryLayer.EPISODIC
            ):
                pass  # episodic 不应被共享，防御性跳过
            else:
                self._private_layers[MemoryLayer.EPISODIC] = episodic[-_DEFAULT_MAX_EPISODIC:]

    def write_shared_record(self, layer: MemoryLayer, record: MemoryRecord) -> None:
        """显式向共享层写入记录（供外部策略/编排代码使用）。"""
        if self._shared_store is None or not self._shared_store.is_shared(layer):
            raise KeyError(f"层 {layer!r} 未配置为共享")
        self._shared_store.add_record(layer, record)

    def query(self, layer: MemoryLayer) -> list[MemoryRecord]:
        """显式查询指定层的记录。共享层走 SharedStore，私有层走本地存储。"""
        return list(self._get_layer_records(layer))

    def get_private_layer_snapshot(self) -> dict[str, Any]:
        """返回私有层的当前状态快照，用于测试和调试。"""
        return {k.value: list(v) for k, v in self._private_layers.items()}
