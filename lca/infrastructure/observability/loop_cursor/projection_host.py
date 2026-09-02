"""StdProjectionHost —— Loop 维度投影宿主(ADR-0170 D2 / D5)。

职责:
- register(def) -> ProjectionToken(disposer 模式)
- drive(snapshot, record)   —— 由 CloseBarrier 在每次 EventSpine.append 后调用
- flush_all()               —— 调用每条 deriver 的 view() 并写 side-effect
- L16 钉死:不订阅 ``writable.iteration.close`` EP(close EP 仅 Persistence 消费)

新增 deriver 零改 ``loop_cursor.py``(I-PROJ-5);默认注册清单由 D5 给出。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.contracts.observability.loop_projection import (
    LoopProjectionDefinition,
    LoopProjectionSnapshot,
    ProjectionToken,
)
from lca.infrastructure.observability.loop_cursor.projections.defaults import (
    default_projection_definitions,
)
from lca.infrastructure.observability.spine.event_record import EventRecord

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlushReport:
    """flush_all 执行结果(ADR-0170 D2)。

    Attributes:
        completed:   成功 flush 的 deriver key 列表(按 drive 注册顺序)。
        failed:      失败 (key, exception) 元组列表 — 隔离失败不传播。
        duration_ms: flush 耗时。
    """

    completed: tuple[str, ...]
    failed: tuple[tuple[str, BaseException], ...]
    duration_ms: int


class StdProjectionHost:
    """默认 ProjectionHost 实现(ADR-0170 D2)。

    Thread-safety:register / dispose / drive / flush_all 由
    ``self._lock`` 串行化(测试中常见的"并发驱动"场景需明确期望)。

    状态:
        _definitions:   key -> LoopProjectionDefinition(registry)
        _states:        key -> 内部 reducer state
        _snapshots:     key -> 最后一次 drive 后的 LoopProjectionSnapshot
        _disposed:      key -> True 表已 dispose(注销后 drive 跳过)
    """

    def __init__(
        self,
        *,
        initial: list[LoopProjectionDefinition] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._definitions: dict[str, LoopProjectionDefinition] = {}
        self._states: dict[str, Any] = {}
        self._snapshots: dict[str, LoopProjectionSnapshot] = {}
        self._disposed: set[str] = set()
        for definition in initial if initial is not None else default_projection_definitions():
            self.register(definition)

    # ── 注册(2):register / unregister(ADR-0170 D2)─────────────
    def register(self, definition: LoopProjectionDefinition) -> ProjectionToken:
        """注册 deriver;返回 disposer token。重复注册同一 key 抛 ValueError。"""
        key = definition.key
        with self._lock:
            if key in self._definitions and key not in self._disposed:
                raise ValueError(f"projection {key!r} already registered")
            self._definitions[key] = definition
            self._disposed.discard(key)
            seed = definition.init()
            self._states[key] = seed
            self._snapshots[key] = LoopProjectionSnapshot(
                state=seed,
                seq=0,
                last_record=None,
                monotonic=True,
            )

            def _dispose() -> None:
                self._disposed.add(key)
                self._definitions.pop(key, None)
                self._states.pop(key, None)
                self._snapshots.pop(key, None)

            return ProjectionToken(key=key, dispose=_dispose)

    def unregister(self, key: str) -> ProjectionToken | None:
        """注销指定 key;返回旧 token 或 None。"""
        with self._lock:
            if key not in self._definitions and key not in self._disposed:
                return None
            token = ProjectionToken(
                key=key,
                dispose=lambda k=key: self._do_dispose(k),
            )
            self._do_dispose(key)
            return token

    def _do_dispose(self, key: str) -> None:
        with self._lock:
            self._disposed.add(key)
            self._definitions.pop(key, None)
            self._states.pop(key, None)
            self._snapshots.pop(key, None)

    # ── 驱动(2):drive / view_snapshot ───────────────────────────
    def drive(self, snapshot: CursorSnapshot, record: EventRecord) -> None:
        """对所有 active deriver 调 apply(state, snapshot, record)。

        L16:本方法不消费 ``writable.iteration.close`` EP ——
        Host 默认清单保证不订阅;由调用方在 drive 前过滤(也由测试断言)。
        """
        with self._lock:
            targets = [
                (k, d, self._states[k])
                for k, d in self._definitions.items()
                if k not in self._disposed
            ]
        for key, definition, prev_state in targets:
            try:
                new_state = definition.apply(prev_state, snapshot, record)
            except Exception as exc:
                log.warning(
                    "projection_host.drive apply failed key=%s err=%s",
                    key,
                    exc,
                    exc_info=True,
                )
                continue
            with self._lock:
                self._states[key] = new_state
                self._snapshots[key] = LoopProjectionSnapshot(
                    state=new_state,
                    seq=record.sequence,
                    last_record=record,
                    monotonic=True,
                )
        # drive 完成后通知 listeners(view 派发;为简单实现,每次 drive 后全量回调)
        self._fire_listeners()

    def _fire_listeners(self) -> None:
        """view_snapshot 变化时通知订阅者(view 派生)。"""
        with self._lock:
            listeners = list(getattr(self, "_listeners", []))
            snap = dict(self._snapshots)
        for listener in listeners:
            try:
                listener(snap)
            except Exception as exc:
                log.warning(
                    "projection_host listener raised err=%s",
                    exc,
                    exc_info=True,
                )

    def view_snapshot(self) -> dict[str, LoopProjectionSnapshot]:
        """返回所有 active deriver 的当前 snapshot(派生视图)。"""
        with self._lock:
            return dict(self._snapshots)

    # ── 订阅(2):subscribe_changes / restore(ADR-0170 D2)─────────
    def subscribe_changes(
        self,
        listener: Callable[[dict[str, Any]], None],
    ) -> Callable[[], None]:
        """订阅 ``view_snapshot()`` 变化;返回 disposer。

        当前实现:每次 drive 后回调一次(行内)。未来可扩展为 diff-based。
        """
        with self._lock:
            self._listeners = getattr(self, "_listeners", [])
            self._listeners.append(listener)

        def _dispose() -> None:
            with self._lock:
                listeners: list[Callable[[dict[str, Any]], None]] = getattr(self, "_listeners", [])
                if listener in listeners:
                    listeners.remove(listener)

        return _dispose

    def restore(
        self,
        *,
        base_seq: int,
        header: dict[str, Any],
        cut: int,
    ) -> None:
        """Checkpoint replay 入口;调用每条 deriver 的 restore(state)。

        ``base_seq`` 是 checkpoint seq;``cut`` 表 replay 截止。
        当前实现按 deriver 的 ``restore(init_state)`` 重置;若 deriver
        未提供则保留当前 state(silent 兼容)。
        """
        with self._lock:
            for key, definition in list(self._definitions.items()):
                if key in self._disposed:
                    continue
                current = self._states.get(key)
                if current is None:
                    continue
                try:
                    restored = definition.restore(current)
                except Exception as exc:
                    log.warning(
                        "projection_host.restore failed key=%s err=%s",
                        key,
                        exc,
                        exc_info=True,
                    )
                    continue
                self._states[key] = restored
                self._snapshots[key] = LoopProjectionSnapshot(
                    state=restored,
                    seq=base_seq,
                    last_record=None,
                    monotonic=True,
                )
            _ = header  # reserved;keep for caller-supplied metadata

    # ── flush / close ─────────────────────────────────────────────
    def flush_all(self) -> FlushReport:
        """对所有 active deriver 调 view(state) 并写 side-effect。

        每条 deriver 独立 try 隔离失败(I-PROJ-3);失败记录到 failed,
        不抛。
        """
        import time

        started_ms = time.monotonic_ns()
        with self._lock:
            targets = [
                (k, d, self._states[k])
                for k, d in self._definitions.items()
                if k not in self._disposed
            ]
        completed: list[str] = []
        failed: list[tuple[str, BaseException]] = []
        for key, definition, state in targets:
            try:
                _ = definition.view(state)
            except Exception as exc:
                failed.append((key, exc))
                log.warning(
                    "projection_host.flush_all view failed key=%s err=%s",
                    key,
                    exc,
                    exc_info=True,
                )
                continue
            completed.append(key)
        duration_ms = (time.monotonic_ns() - started_ms) // 1_000_000
        return FlushReport(
            completed=tuple(completed),
            failed=tuple(failed),
            duration_ms=duration_ms,
        )

    def close(self) -> FlushReport:
        """CloseBarrier 在 L7-4 之后(L7-5 之前)可选调用;同 flush_all。"""
        return self.flush_all()

    # ── 内省 ──────────────────────────────────────────────────────
    def active_keys(self) -> tuple[str, ...]:
        """返回当前 active deriver key 列表(测试 seam)。"""
        with self._lock:
            return tuple(k for k in self._definitions if k not in self._disposed)


__all__ = ["FlushReport", "StdProjectionHost"]
