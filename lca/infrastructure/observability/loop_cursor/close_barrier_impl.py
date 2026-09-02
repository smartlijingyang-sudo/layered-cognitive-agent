"""StdCloseBarrier —— close 时序协同器(ADR-0169 D5 / L7-1..L7-6)。

5 步顺序:

  1. cursor.close signal → 关状态机
  2. emit ``writable.iteration.closing`` EP
  3. Persistence.flush() → ProjectionHost.flush_all()
  4. emit ``writable.iteration.close`` EP(L16:仅 Persistence 消费;
     ProjectionHost 不订阅,防"投影已关"竞态)
  5. release

L16 钉死:ProjectionHost.flush_all() 在 close EP emit **之后**,
保证 close EP 走完 persistence 后才批写投影;**任何**写入投影试图
订阅 close EP 的行为由架构测试拦截(I-PROJ-4)。
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from lca.contracts.observability.close_barrier import CloseReason, CloseReport

log = logging.getLogger(__name__)


@runtime_checkable
class _Persistence(Protocol):
    """PersistenceCoordinator 协议最小面(用于 barrier 注入)。"""

    def flush(self) -> bool: ...


@runtime_checkable
class _Host(Protocol):
    """ProjectionHost 协议最小面。"""

    def flush_all(self) -> object: ...


@runtime_checkable
class _CloseEmitter(Protocol):
    """写 close EP 的最小接口(EventSpine / StdLoopCursor 都满足)。"""

    def emit_close(self, reason: CloseReason) -> None: ...


class StdCloseBarrier:
    """CloseBarrier 默认实现(ADR-0169 D5)。

    协作组件全部由构造器注入;Loose coupling,故障注入友好(评审潜在 #16)。
    """

    def __init__(
        self,
        *,
        persistence: _Persistence,
        host: _Host,
        close_emitter: _CloseEmitter,
    ) -> None:
        self._persistence = persistence
        self._host = host
        self._emitter = close_emitter

    def close(self, reason: CloseReason) -> CloseReport:
        """按 5 步顺序执行 close 协调;异常隔离,返回 CloseReport。

        Step 1:关状态机 = cursor.close() 由调用方在调本方法前完成(本组件不持 cursor)。
        Step 2:closing EP emit 由 cursor 自己在 close() 时 append;
                PersistenceCoordinator 接收后触发 flush 决策(D5 / L7-2)。
        Step 3a:persistence.flush() —— 阻塞;失败不抛,记 persistence_error。
        Step 3b:host.flush_all()   —— 阻塞;失败不抛,记 projections_error。
                ↑↑ 顺序钉死:persistence 先, projections 后。
        Step 4:close EP emit —— 失败记 close_emit_error。
        Step 5:release —— 本组件无外部资源,由 GC 收。
        """
        persistence_flushed = False
        persistence_error: BaseException | None = None
        try:
            self._persistence.flush()
            persistence_flushed = True
        except Exception as exc:
            persistence_error = exc
            log.warning("close_barrier persistence.flush failed: %s", exc, exc_info=True)

        projections_flushed = False
        projections_error: BaseException | None = None
        try:
            self._host.flush_all()
            projections_flushed = True
        except Exception as exc:
            projections_error = exc
            log.warning("close_barrier host.flush_all failed: %s", exc, exc_info=True)

        close_emitted = False
        close_emit_error: BaseException | None = None
        try:
            self._emitter.emit_close(reason)
            close_emitted = True
        except Exception as exc:
            close_emit_error = exc
            log.warning("close_barrier emit_close failed: %s", exc, exc_info=True)

        return CloseReport(
            reason=reason,
            persistence_flushed=persistence_flushed,
            projections_flushed=projections_flushed,
            close_emitted=close_emitted,
            persistence_error=persistence_error,
            projections_error=projections_error,
            close_emit_error=close_emit_error,
        )


__all__ = ["StdCloseBarrier"]
