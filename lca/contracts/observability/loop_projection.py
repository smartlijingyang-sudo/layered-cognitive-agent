"""LoopProjectionDefinition Protocol + Snapshot + Token(ADR-0170 D1)。

Loop 维度可插拔投影契约;与 ADR-0063 session 维度 ProjectionDefinition 并存,
互不替代。新增 deriver 零改 `loop_cursor.py`(I-PROJ-5)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.infrastructure.observability.spine.event_record import EventRecord


@dataclass(frozen=True)
class LoopProjectionSnapshot:
    """Projection 消费的只读视图(ADR-0170 D1)。

    Attributes:
        state:         该 deriver 派生的当前 reducer state。
        seq:           最后一次 drive 触发该 deriver 的 event sequence。
        last_record:   触发该 deriver 的最后一条 EventRecord(可能为 None)。
        monotonic:     True ⇒ 该 deriver 仅追加,可安全 replay。
    """

    state: Any
    seq: int
    last_record: EventRecord | None
    monotonic: bool


@runtime_checkable
class LoopProjectionDefinition(Protocol):
    """Loop 维度纯 reducer(ADR-0170 D1)。

    cursor 是事件源;projection 是订阅者(由 ProjectionHost.drive 调用)。
    副作用(写 journal.json / narrative.md)由 ``view`` 派生,**不在** apply 内。
    """

    key: str
    version: int

    def init(self) -> Any:
        """Seed 状态;每次 register 调一次。"""

    def apply(self, state: Any, snapshot: CursorSnapshot, record: EventRecord) -> Any:
        """纯 reducer;in-place 修改禁止(返回新 state);不抛副作用。"""

    def view(self, state: Any) -> Any:
        """派生 side-effect target;Host.flush_all 在此才真正写盘。"""

    def restore(self, state: Any) -> Any:
        """Checkpoint replay 入口;默认 = init。"""


@dataclass(frozen=True)
class ProjectionToken:
    """Disposer handle — 由 ProjectionHost.register 返回。

    dispose() 调用后,该 deriver 立刻从 host 的 active set 中消失,
    后续 drive 不再被调用。Token 本身是 frozen;disposed 状态由 host
    内部追踪(同一 token 重复 dispose 是 no-op)。
    """

    key: str
    dispose: Any  # Callable[[], None] — host-managed disposer


__all__ = [
    "LoopProjectionDefinition",
    "LoopProjectionSnapshot",
    "ProjectionToken",
]
