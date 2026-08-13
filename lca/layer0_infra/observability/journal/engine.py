"""ExecutionJournal —— 执行日志核心引擎（ADR-0037 Journal-as-Truth）。

单一职责：append-only 日志的写入端。
``record(JournalEvent)`` 流水线：
    ① 词表校验 —— 未登记事件类 fail-fast（显式异常）；
    ② 关联骨架盖章 —— ambient ``RunScope``（trace/run/parent/delegation id）；
    ③ 属性策略写入期强制 —— 字符串字段统一脱敏/截断（发射点不需要自觉）；
    ④ 顺序扇出投影器 —— 故障隔离：单投影器异常只记 structlog，不中断 run。

日志流在内存中全量保留（per hub），供 InsightEngine 与终态投影消费。
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Sequence
from enum import Enum
from typing import Any

import structlog

from lca.contracts.models.observability.journal import (
    JournalEvent,
    RunScope,
    StampedEvent,
    get_current_run_scope,
)
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.observability.policy import AttributePolicy

_log = structlog.get_logger("lca.journal")


class UnregisteredJournalEventError(TypeError):
    """发射了未在 ``JOURNAL_EVENT_CLASSES`` 登记的 journal 事件类型。"""

    def __init__(self, event_type: type) -> None:
        known = ", ".join(sorted(JOURNAL_EVENT_CLASSES))
        super().__init__(f"未登记的 journal 事件 {event_type.__name__}；词表：{known}")


class _IsolatedProjector(JournalProjector):
    """故障隔离包装：投影异常只记日志，永不向上传播（与导出器同构）。"""

    def __init__(self, inner: JournalProjector) -> None:
        self._inner = inner

    @property
    def inner(self) -> JournalProjector:
        return self._inner

    def on_event(self, stamped: StampedEvent) -> None:
        try:
            self._inner.on_event(stamped)
        except Exception:
            _log.warning(
                "journal_projector_failed",
                projector=type(self._inner).__name__,
                event_type=type(stamped.event).__name__,
            )

    def flush(self) -> None:
        try:
            self._inner.flush()
        except Exception:
            _log.warning("journal_flush_failed", projector=type(self._inner).__name__)

    def close(self) -> None:
        try:
            self._inner.close()
        except Exception:
            _log.warning("journal_close_failed", projector=type(self._inner).__name__)


class ExecutionJournal:
    """append-only 执行日志：盖章 → 策略强制 → 扇出投影器。"""

    def __init__(
        self,
        projectors: Sequence[JournalProjector] = (),
        *,
        policy: AttributePolicy | None = None,
    ) -> None:
        self._projectors = [_IsolatedProjector(p) for p in projectors]
        self._policy = policy if policy is not None else AttributePolicy()
        self._events: list[StampedEvent] = []
        self._seq = 0

    @property
    def events(self) -> tuple[StampedEvent, ...]:
        """已记录的盖章事件流（只读快照）。"""
        return tuple(self._events)

    def record(self, event: JournalEvent) -> StampedEvent:
        """记录一条 journal 事件并扇出投影器（返回盖章记录）。"""
        event_type = type(event)
        if event_type.__name__ not in JOURNAL_EVENT_CLASSES:
            raise UnregisteredJournalEventError(event_type)
        self._seq += 1
        scope = get_current_run_scope() or RunScope()
        sanitized = self._apply_policy(event)
        stamped = StampedEvent(seq=self._seq, ts=time.time(), scope=scope, event=sanitized)
        self._events.append(stamped)
        for projector in self._projectors:
            projector.on_event(stamped)
        self._emit_followups()
        return stamped

    def _emit_followups(self) -> None:
        """Projectors are readers. Follow-up events publish after fan-out.

        InsightEngine used to call record() mid-fan-out, so later readers
        saw RunInsight before AgentRunFinished (seq inversion).
        """
        followups: list[JournalEvent] = []
        for projector in self._projectors:
            inner = getattr(projector, "inner", projector)
            drain = getattr(inner, "drain_followups", None)
            if callable(drain):
                followups.extend(drain())
        for event in followups:
            self.record(event)

    def _apply_policy(self, event: JournalEvent) -> JournalEvent:
        """字符串字段写入期策略强制（脱敏/预览裁剪/截断）；非字符串原样。

        枚举（含 ``str`` 混入的词表枚举）归一为纯值——投影/渲染侧
        永不见到 ``ActionType.XXX`` 之类的 repr 泄漏。
        """
        updates: dict[str, Any] = {}
        has_output_truncated = any(f.name == "output_truncated" for f in dataclasses.fields(event))
        for item in dataclasses.fields(event):
            value = getattr(event, item.name)
            if isinstance(value, Enum):
                updates[item.name] = value.value
                continue
            if not isinstance(value, str):
                continue
            journal_kind = item.metadata.get("journal_kind")
            if journal_kind == "content":
                prepared, truncated = self._policy.prepare_content(item.name, value)
                updates[item.name] = prepared if prepared is not None else ""
                if truncated and has_output_truncated:
                    updates["output_truncated"] = True
            else:
                prepared_map = self._policy.prepare({item.name: value})
                updates[item.name] = prepared_map.get(item.name, "")
        return dataclasses.replace(event, **updates) if updates else event

    def flush(self) -> None:
        for projector in self._projectors:
            projector.flush()

    def close(self) -> None:
        self.flush()
        for projector in self._projectors:
            projector.close()
