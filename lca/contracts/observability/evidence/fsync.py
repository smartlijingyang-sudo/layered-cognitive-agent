"""append 型持久化的 fsync 节奏契约(闭集)。

"何时 fsync" 是契约,不是实现细节:落盘方必须从 :class:`FsyncProtocol`
取一个值显式声明自己的节奏,行为从契约派生,禁止隐式语义或平行枚举
(见 docs/notes/proposed/seam/2026-09-03-2-seam-fsync-semantics.md)。

本模块零依赖(纯数据契约);``lca.contracts.observability.ssot`` 对其
re-export,实现侧(FileSink / TracingFileSink / lca_kernel persistence)
直接从本模块导入。
"""

from __future__ import annotations

from enum import Enum


class FsyncProtocol(str, Enum):
    """append 型 fd 的 fsync 节奏契约(闭集)。

    声明单个 append fd "何时 fsync",决定进程崩溃 / SIGKILL / 断电时
    的丢数据上界。任何走 append 落盘的实现(观测面 sinks、
    ``lca_kernel.events`` persistence observer、未来新 sink)必须从本
    枚举取一个值显式声明自己的节奏;**禁止**无声明的隐式语义,
    **禁止**在实现层另造平行枚举。

    取值与丢失上界:

    - ``PER_WRITE``:每次 append 后立即 fsync(对齐 DSH
      ``session-persistence-jsonl`` 的 ``handle.sync()`` 形态)。
      丢失上界 = 0 条;写放大最大,只用于正确性优先于吞吐的路径
      (异常兜底日志)。
    - ``BATCH``:累计条数或时间间隔达到阈值时 fsync 一次。丢失上界
      = 阈值窗口内的条数;吞吐 / 丢失折中,spine 主账本默认。
    - ``COMMIT``:仅 ``close`` 时 fsync 一次。丢失上界 = open 以来的
      全部条数;只用于低频、内容在别处已有副本的辅助文件
      (exceptions 索引的条目同时落在 sidecar,丢索引尾部只伤
      grep 分诊,不丢证据本体)。

    所有权:本枚举是 L1 契约 SSOT;实现方只读不改。失败语义
    (fsync 抛 OSError 时静默日志还是上抛)由各 sink 在自己的契约里
    声明,不属于本枚举。
    """

    PER_WRITE = "per_write"
    BATCH = "batch"
    COMMIT = "commit"


__all__ = ["FsyncProtocol"]
