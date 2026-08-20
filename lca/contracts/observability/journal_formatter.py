"""Journal formatter Protocol（ADR-0063 PR-9 + 清理 B）。

``JournalFormatter`` 是 backend-agnostic 的 StampedEvent → 字符串/字节序列化器；
ConsoleJournalProjector / FactStreamProjector / JsonlJournalProjector 都是它的实现。

新增展示后端（markdown / csv / parquet）= 一个 ``@plugin`` 注册到 ``journal_formatter``
seam；不需修改 ``BoundObservability`` 装配路径。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lca.contracts.models.observability.journal import StampedEvent


@runtime_checkable
class JournalFormatter(Protocol):
    """把已盖章事件渲染为字符串/字节；每个 formatter 决定自己的 verbosity 行为。"""

    @property
    def name(self) -> str:
        """formatter 注册名（如 'console' / 'fact_stream' / 'jsonl'）。"""

    def render_event(self, stamped: StampedEvent) -> str:
        """渲染单条事件为字符串（含末尾换行）。"""

    def flush(self) -> str:
        """冲刷内部缓冲，返回未发送的字符串（空字符串表示已 flush）。"""

    def close(self) -> str:
        """关闭 formatter，返回终结片段（如 SSE sentinel / JSONL 末尾空行）。"""
