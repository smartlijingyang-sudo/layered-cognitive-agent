"""EventIdentity provider protocol —— ADR-0096 MVA-2 + ADR-0097."""

from __future__ import annotations

from typing import Protocol


class EventIdentityProvider(Protocol):
    """给定 (run_id, seq, event_type) 派生全局唯一 event_id。

    实现约束（I3 + ADR-0097）：
    - 派生函数不接 float ts 参数（构造时闭环派生）
    - 调用方应以关键字传入 run_id / seq / event_type
    - ULID 实现每次调用产新的全局唯一 id（monotonic ms + 随机分量）
    """

    def derive(self, *, run_id: str, seq: int, event_type: str) -> str: ...
