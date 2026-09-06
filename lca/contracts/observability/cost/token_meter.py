"""Token 计量契约 —— DSH token-meter 快照形态（纯观察面 Protocol）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "TokenMeter",
    "TokenMeterNode",
    "TokenMeterSnapshot",
]


@dataclass(frozen=True, slots=True)
class TokenMeterNode:
    """surface 上一个节点的计量条目。"""

    seq: int
    estimated_tokens: int
    kind: str = "estimated"


@dataclass(frozen=True, slots=True)
class TokenMeterSnapshot:
    """``measure(session)`` 输出（对齐 DSH token-meter types）。"""

    log_revision: int
    baseline: int
    surface_delta_tokens: int
    total_tokens: int
    surface_tokens: int
    nodes: tuple[TokenMeterNode, ...] = ()
    shadowed_token_count: int = 0
    baseline_kind: str = "estimated"


@runtime_checkable
class TokenMeter(Protocol):
    """从 Session 事件 fold 的纯函数计量 seam。"""

    def measure(self, session: Any, *, header: dict[str, Any] | None = None) -> TokenMeterSnapshot:
        """增量 replay;``header`` 与 baseline 一致时可锚定 provider usage。"""
        ...
