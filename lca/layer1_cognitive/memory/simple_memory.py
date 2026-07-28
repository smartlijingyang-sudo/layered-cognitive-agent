"""四类记忆的最小实现：内存列表存储 + 简单相关性检索 + 可选团队共享。"""

from __future__ import annotations

import uuid
from typing import Any

from lca.contracts.decision import Observation, Reflection
from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols import MemorySystem
from lca.contracts.state import TypedState
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SimpleMemorySystem(MemorySystem):
    """Working / Semantic / Episodic / Procedural 四层记忆。

    可选绑定 TeamSharedMemoryStore：对声明共享的层（semantic/procedural），
    读写直接走共享 store，实现跨 Agent 记忆共享；未声明共享的层保持私有。
    """

    def __init__(self) -> None:
        self._shared_store: TeamSharedMemoryStore | None = None
        self._private_layers: dict[str, list[MemoryRecord]] = {
            "working": [],
            "semantic": [],
            "episodic": [],
            "procedural": [],
        }

    def bind_shared_store(self, store: TeamSharedMemoryStore) -> None:
        """绑定团队共享记忆存储。共享层的数据读写委托给 store。"""
        self._shared_store = store

    def _get_layer_records(self, layer: str) -> list[MemoryRecord]:
        if self._shared_store is not None and self._shared_store.is_shared(layer):
            return self._shared_store.get_records(layer)
        return self._private_layers[layer]

    def _append_record(self, layer: str, record: MemoryRecord) -> None:
        if self._shared_store is not None and self._shared_store.is_shared(layer):
            self._shared_store.add_record(layer, record)
        else:
            self._private_layers[layer].append(record)

    async def perceive_and_retrieve(self, state: TypedState) -> TypedState:
        records: list[MemoryRecord] = []
        for layer_name in self._private_layers:
            records.extend(self._get_layer_records(layer_name))
        state.retrieved_context = records
        return state

    async def update_multi_level(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None:
        if observation.payload is not None and observation.success:
            # 追加到 working memory 而非覆盖，确保多步委派历史对 agent 可见
            self._private_layers["working"].append(
                MemoryRecord(
                    record_id=_new_id("mem"),
                    content=f"TOOL_RESULT: {observation.payload}",
                    memory_type="working",
                    importance=0.9,
                    source_trace_id=state.trace_id,
                )
            )
            # 防止 working memory 无限增长：保留最近 20 条
            max_working = 20
            if len(self._private_layers["working"]) > max_working:
                self._private_layers["working"] = self._private_layers["working"][-max_working:]
        self._append_record(
            "episodic",
            MemoryRecord(
                record_id=_new_id("mem"),
                content=f"step={state.step} success={observation.success} verdict={reflection.verdict}",
                memory_type="episodic",
                importance=0.5,
                source_trace_id=state.trace_id,
            ),
        )
        await self.compress()

    async def compress(self) -> None:
        max_episodic = 50
        episodic = self._get_layer_records("episodic")
        if len(episodic) > max_episodic:
            if self._shared_store is not None and self._shared_store.is_shared("episodic"):
                pass  # episodic 不应被共享，防御性跳过
            else:
                self._private_layers["episodic"] = episodic[-max_episodic:]

    def write_shared_record(self, layer: str, record: MemoryRecord) -> None:
        """显式向共享层写入记录（供外部策略/编排代码使用）。"""
        if self._shared_store is None or not self._shared_store.is_shared(layer):
            raise KeyError(f"层 {layer!r} 未配置为共享")
        self._shared_store.add_record(layer, record)

    def get_private_layer_snapshot(self) -> dict[str, Any]:
        """返回私有层的当前状态快照，用于测试和调试。"""
        return {k: list(v) for k, v in self._private_layers.items()}
