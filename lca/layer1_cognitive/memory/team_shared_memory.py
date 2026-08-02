"""TeamSharedMemoryStore —— 团队级共享记忆存储。

只对 semantic / procedural 两层做跨 Agent 共享（CoALA 记忆分类的语义边界：
episodic 是个体的情景经历，working 是当前会话上下文，这两层保持私有）。
"""

from __future__ import annotations

from lca.contracts.enums import SHAREABLE_LAYERS, MemoryLayer
from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols import SharedMemoryStore


class TeamSharedMemoryStore(SharedMemoryStore):
    """跨 Agent 共享的记忆存储，按 layer 分流。

    每个 layer 维护独立的记录列表，多个 SimpleMemorySystem 实例
    持有同一 store 的引用，实现"共享即同一数据源"。
    """

    def __init__(self, shared_layers: list[MemoryLayer]) -> None:
        invalid = set(shared_layers) - SHAREABLE_LAYERS
        if invalid:
            raise ValueError(f"只有 semantic/procedural 层可以共享，非法层: {invalid}")
        self._shared_layers: list[MemoryLayer] = list(shared_layers)
        self._stores: dict[MemoryLayer, list[MemoryRecord]] = {layer: [] for layer in shared_layers}

    @property
    def shared_layers(self) -> list[MemoryLayer]:
        return list(self._shared_layers)

    def is_shared(self, layer: MemoryLayer) -> bool:
        return layer in self._stores

    def add_record(self, layer: MemoryLayer, record: MemoryRecord) -> None:
        if layer not in self._stores:
            raise KeyError(f"层 {layer!r} 不在共享范围内")
        self._stores[layer].append(record)

    def get_records(self, layer: MemoryLayer) -> list[MemoryRecord]:
        if layer not in self._stores:
            raise KeyError(f"层 {layer!r} 不在共享范围内")
        return list(self._stores[layer])
