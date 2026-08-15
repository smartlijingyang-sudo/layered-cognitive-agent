"""RunStore —— 唯一写入仲裁（ADR-0055 不变量 N1, N2）。

Append-only run fact log。一个 run 的所有事实只通过一个入口写入。

写入流水线：
    ① 词表校验 —— 未登记事件类 fail-fast；
    ② 关联骨架盖章 —— ambient RunScope 或显式 scope；
    ③ 属性策略写入期强制 —— 字符串字段统一脱敏/截断；
    ④ 原子入 log（commit boundary）；
    ⑤ post-commit 通知所有 subscriber（失败隔离，不影响 append 返回值）。

关键不变量：
- N1 append-before-observe：subscriber 永不可见未提交事件。
- N2 seq = log.length：序号由 log 长度唯一确定，连续不跳跃。

设计来源：DSH Session.append()（同步原子 + post-commit 通知）、
EventStore expected-version CAS（并发控制）、
Kafka consumer-managed offset（观察者自拉）。
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


class _IsolatedSubscriber(JournalProjector):
    """故障隔离包装：subscriber 异常只记日志，永不向上传播。"""

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
                "journal_subscriber_failed",
                subscriber=type(self._inner).__name__,
                event_type=type(stamped.event).__name__,
            )

    def flush(self) -> None:
        try:
            self._inner.flush()
        except Exception:
            _log.warning("journal_flush_failed", subscriber=type(self._inner).__name__)

    def close(self) -> None:
        try:
            self._inner.close()
        except Exception:
            _log.warning("journal_close_failed", subscriber=type(self._inner).__name__)


class RunStore:
    """Append-only run fact log。不变量 N1 + N2。

    一个 run 的所有事实只通过 ``append()`` 写入。写入后立即通知所有
    subscriber；subscriber 异常被隔离，不影响 append 返回值。
    """

    def __init__(
        self,
        subscribers: Sequence[JournalProjector] = (),
        *,
        policy: AttributePolicy | None = None,
    ) -> None:
        self._subscribers = [_IsolatedSubscriber(s) for s in subscribers]
        self._policy = policy if policy is not None else AttributePolicy()
        self._events: list[StampedEvent] = []
        self._seq = 0

    @property
    def events(self) -> tuple[StampedEvent, ...]:
        """已提交事件的只读快照。"""
        return tuple(self._events)

    @property
    def seq(self) -> int:
        """下一条事件的 seq（= len(log)）。"""
        return self._seq

    def append(self, event: JournalEvent) -> StampedEvent:
        """原子写入：校验 → 盖章 → 策略 → 入 log → post-commit 通知。

        subscriber 通知在 append 成功后，subscriber 失败不影响返回值。
        """
        event_type = type(event)
        if event_type.__name__ not in JOURNAL_EVENT_CLASSES:
            raise UnregisteredJournalEventError(event_type)
        self._seq += 1
        scope = get_current_run_scope() or RunScope()
        sanitized = self._apply_policy(event)
        stamped = StampedEvent(seq=self._seq, ts=time.time(), scope=scope, event=sanitized)
        self._events.append(stamped)  # ← commit boundary
        for subscriber in self._subscribers:
            subscriber.on_event(stamped)
        return stamped

    def read_from(self, after_seq: int) -> Sequence[StampedEvent]:
        """观察者自拉：返回 seq > after_seq 的所有已提交事件。"""
        return tuple(e for e in self._events if e.seq > after_seq)

    def flush(self) -> None:
        for subscriber in self._subscribers:
            subscriber.flush()

    def close(self) -> None:
        self.flush()
        for subscriber in self._subscribers:
            subscriber.close()

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
