"""L0 持久化基础设施 —— 共享的 write-behind 批量写入机制。

Journal 和 Session 的持久化都应通过本模块的 ``WriteBehindBuffer`` 落盘，
而不是各自实现逐条写入。写入路径：

    append → 内存 buffer → 定时/显式触发 → 批量写 → 单次 fsync

失败语义（对齐 DSH ``SessionWriteBehind``）：

- 写入失败 → 事件保留在 pending buffer，等待下次触发或显式 ``flush()``
- ``REQUIRED`` 事件不丢弃；``BEST_EFFORT`` 事件在背压下可丢弃并记聚合计数
- ``dispose()`` 排空全部待写事件后关闭 sink
"""

from lca.infrastructure.persistence.jsonl_sink import JsonlFileSink
from lca.infrastructure.persistence.write_behind import (
    DropPolicy,
    WriteBehindBuffer,
    WriteBehindSink,
)

__all__ = [
    "DropPolicy",
    "JsonlFileSink",
    "WriteBehindBuffer",
    "WriteBehindSink",
]
