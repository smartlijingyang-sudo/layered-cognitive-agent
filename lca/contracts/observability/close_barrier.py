"""CloseBarrier Protocol + CloseReport(ADR-0169 D5 / L7-1..L7-6)。

CloseBarrier 是独立组件;由 ObservabilityRuntime 持有。协调 5 步顺序:

    1. cursor.close signal → 关状态机
    2. emit ``writable.iteration.closing`` EP
    3. Persistence.flush() → ProjectionHost.flush_all()
       顺序由 Barrier 协调
    4. emit ``writable.iteration.close`` EP(L16:仅 Persistence 消费;
       ProjectionHost 不订阅,防"投影已关"竞态)
    5. release

cursor 不再直接持有 Persistence / ProjectionHost 实例 —— 它只发 closing
信号,由 CloseBarrier 解耦编排(ADR-0169 D5)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

CloseReason = Literal[
    "completed",
    "user_stop",
    "budget_exhausted",
    "approval_pending",
    "approval_rejected",
    "error",
    "loop_guard",
    "kernel_shutdown",
]


@dataclass(frozen=True)
class CloseReport:
    """CloseBarrier.coordinate 完成的执行报告。

    Attributes:
        reason:                触发 close 的原因(来自 cursor.close(reason))。
        persistence_flushed:   Persistence.flush() 是否成功。
        projections_flushed:   ProjectionHost.flush_all() 是否成功。
        close_emitted:         ``writable.iteration.close`` EP 是否成功 emit。
        persistence_error:     Persistence.flush 异常(若失败)。
        projections_error:     ProjectionHost.flush_all 异常(若失败)。
        close_emit_error:      close EP emit 异常(若失败)。
    """

    reason: CloseReason
    persistence_flushed: bool
    projections_flushed: bool
    close_emitted: bool
    persistence_error: BaseException | None = None
    projections_error: BaseException | None = None
    close_emit_error: BaseException | None = None


@runtime_checkable
class CloseBarrier(Protocol):
    """Close 时序协同器(ADR-0169 D5 / L7-1..L7-6)。

    钉死不变量:
    L7-1 cursor 状态机 close
    L7-2 ``writable.iteration.closing`` EP emit
    L7-3 Persistence.flush() + sink close
    L7-4 ProjectionHost.flush_all() ← 默认批写窗口
    L7-5 ``writable.iteration.close`` EP emit(L16:仅 Persistence 写入;
         ProjectionHost **不**订阅)
    L7-6 release
    """

    def close(self, reason: CloseReason) -> CloseReport:
        """按 5 步顺序执行 close 协调;返回 CloseReport。"""
