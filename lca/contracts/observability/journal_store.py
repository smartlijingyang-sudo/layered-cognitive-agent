"""Journal store backend Protocol（ADR-0063 PR-8）。

``RunStore`` 把"事件账本存储"职责抽到 ``JournalStoreBackend`` 后面；
in-memory 是当前唯一实现，文件 backed / 远端等是后续 PR 的 Plugin 扩展点。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lca.contracts.models.observability.journal import StampedEvent


@runtime_checkable
class JournalStoreBackend(Protocol):
    """Append-only 事件账本后端契约。

    实现要点：
    - ``append`` 返回已分配 ``seq`` 的不可变 ``StampedEvent``（构造在 backend 内完成
      是合理选择，但本 Protocol 把构造留给 caller，以保留 policy 阶段的位置）。
    - ``events`` 返回稳定 tuple 快照，便于消费者无需自拷贝。
    - ``get`` / ``read_from`` O(1) 读单条与按 seq 范围拉取。
    - ``flush`` / ``close`` 是可选能力；纯内存实现可空操作。
    """

    def append(self, stamped: StampedEvent) -> StampedEvent:
        """追加已盖章事件；返回同一对象以允许 caller 链式使用。"""

    def events(self) -> Sequence[StampedEvent]:
        """全部已提交事件的稳定快照。"""

    def get(self, seq: int) -> StampedEvent | None:
        """按连续序列 O(1) 读取；越界返回 None。"""

    def read_from(self, after_seq: int) -> Sequence[StampedEvent]:
        """返回严格晚于 ``after_seq`` 的事件，供可恢复消费者拉取。"""

    def flush(self) -> None:
        """请求可缓冲后端提交其自身的输出。"""

    def close(self) -> None:
        """关闭后端；重复调用安全。"""
