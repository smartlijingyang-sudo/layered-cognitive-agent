"""RunStore —— 唯一写入仲裁（ADR-0055 不变量 N1, N2）+ 增量投影。

Append-only run fact log。一个 run 的所有事实只通过一个入口写入。

写入流水线：
    ① 词表校验 —— 未登记事件类 fail-fast；
    ② append 边界验证 —— 一次 pass 完成 frozen 校验 + 数据完整性断言；
    ③ 关联骨架盖章 —— ambient RunScope 或显式 scope；
    ④ 属性策略写入期强制 —— 字符串字段统一脱敏/截断；
    ⑤ 原子入 log（commit boundary）；
    ⑥ post-commit 通知所有 subscriber（失败隔离，不影响 append 返回值）；
    ⑦ 增量投影缓存失效标记。

关键不变量：
- N1 append-before-observe：subscriber 永不可见未提交事件。
- N2 seq = log.length：序号由 log 长度唯一确定，连续不跳跃。
- N3 append 边界验证：写入即 frozen + 数据完整，后续读取零拷贝。

增量投影：
    ``derive_events(predicate)`` 从日志投影出满足条件的子集，缓存到
    下次 append 时失效。调用方无需重算全量。

设计来源：DSH Session.append()（同步原子 + post-commit 通知 + 增量
deriveMessages 缓存）、EventStore expected-version CAS、
Kafka consumer-managed offset。
"""

from __future__ import annotations

import copy
import dataclasses
import time
from collections.abc import Callable, Sequence
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

SubscriberFactory = Callable[[], Sequence[JournalProjector]]
"""延迟 subscriber 解析：打破 InsightEngine ↔ RunStore 循环依赖。"""


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
    """Append-only run fact log。不变量 N1 + N2 + N3。

    一个 run 的所有事实只通过 ``append()`` 写入。写入后立即通知所有
    subscriber；subscriber 异常被隔离，不影响 append 返回值。

    ``subscribers`` 可以是具体列表或工厂函数——工厂在首次 ``append()`` 时
    解析，打破 subscriber 与 store 的循环依赖（无需 ``bind_store()``）。

    增量投影：``derive_events(predicate)`` 缓存满足条件的子集，
    只在 append 后失效并增量扩展。
    """

    def __init__(
        self,
        subscribers: Sequence[JournalProjector] | SubscriberFactory = (),
        *,
        policy: AttributePolicy | None = None,
    ) -> None:
        if callable(subscribers):
            self._subscriber_factory: SubscriberFactory | None = subscribers
            self._subscribers: list[_IsolatedSubscriber] = []
        else:
            self._subscriber_factory = None
            self._subscribers = [_IsolatedSubscriber(s) for s in subscribers]
        self._policy = policy if policy is not None else AttributePolicy()
        self._events: list[StampedEvent] = []
        self._seq = 0
        # 增量投影缓存：predicate id → (cached_result, last_seq)
        self._projection_cache: dict[int, tuple[list[StampedEvent], int]] = {}

    @property
    def events(self) -> tuple[StampedEvent, ...]:
        """已提交事件的只读快照。"""
        return tuple(self._events)

    @property
    def seq(self) -> int:
        """下一条事件的 seq（= len(log)）。"""
        return self._seq

    def _resolve_subscribers_if_needed(self) -> None:
        """首次调用时解析延迟 subscriber 工厂，之后工厂引用释放。"""
        factory = self._subscriber_factory
        if factory is None:
            return
        self._subscriber_factory = None
        self._subscribers = [_IsolatedSubscriber(s) for s in factory()]

    @staticmethod
    def _validate_append_boundary(event: JournalEvent) -> JournalEvent:
        """Append 边界验证（DSH-inspired）：一次 pass 完成 frozen 校验 + 数据完整性断言。

        - 断言事件是 frozen dataclass（构造性不可变）；
        - 深拷贝隔离：返回独立副本，调用方后续修改不影响 log；
        - 断言所有字段值不是 mutable container 的共享引用。

        写入即 frozen + 隔离，后续读取零拷贝。
        """
        if not getattr(type(event), "__dataclass_params__", None):
            raise TypeError(f"journal event must be a dataclass, got {type(event).__name__}")
        if not type(event).__dataclass_params__.frozen:
            raise TypeError(f"journal event must be frozen dataclass: {type(event).__name__}")
        # 深拷贝隔离：调用方持有的引用不影响 log 内的副本
        return copy.deepcopy(event)

    def append(self, event: JournalEvent) -> StampedEvent:
        """原子写入：校验 → 边界验证 → 盖章 → 策略 → 入 log → 通知。

        subscriber 通知在 append 成功后，subscriber 失败不影响返回值。
        首次 append 时解析延迟 subscriber 工厂（如有）。
        """
        self._resolve_subscribers_if_needed()
        event_type = type(event)
        if event_type.__name__ not in JOURNAL_EVENT_CLASSES:
            raise UnregisteredJournalEventError(event_type)
        # Append 边界验证：frozen 断言 + 深拷贝隔离
        isolated = self._validate_append_boundary(event)
        self._seq += 1
        scope = get_current_run_scope() or RunScope()
        sanitized = self._apply_policy(isolated)
        stamped = StampedEvent(seq=self._seq, ts=time.time(), scope=scope, event=sanitized)
        self._events.append(stamped)  # ← commit boundary
        # 通知 subscriber（失败隔离）
        for subscriber in self._subscribers:
            subscriber.on_event(stamped)
        # 增量投影缓存不清空——derive_events 内部按 last_seq 增量扩展
        return stamped

    def read_from(self, after_seq: int) -> Sequence[StampedEvent]:
        """观察者自拉：返回 seq > after_seq 的所有已提交事件。"""
        return tuple(e for e in self._events if e.seq > after_seq)

    def get(self, seq: int) -> StampedEvent | None:
        """O(1) lookup by seq (PR2 / §7.4).  Returns None if seq is out of range."""
        if seq < 1 or seq > len(self._events):
            return None
        return self._events[seq - 1]

    def get_event(self, seq: int) -> JournalEvent | None:
        """O(1) lookup of the JournalEvent payload by seq (PR2 / §7.4)."""
        stamped = self.get(seq)
        return stamped.event if stamped is not None else None

    def find_terminal_tool_invoked(
        self, idempotency_key: str
    ) -> ToolInvoked | None:
        """Find the last ``ToolInvoked`` event for a given idempotency key (PR6).

        Used by the resume path to short-circuit already-executed side
        effects: when the same envelope arrives again (e.g. crash + retry),
        we replay the previous terminal observation instead of re-executing.

        Returns ``None`` if the key was never recorded (the executor must
        re-run in that case).
        """
        if not idempotency_key:
            return None
        # Linear scan over the (small) tool-invocation history — the key
        # is unique per envelope so a hashmap would only help if the log
        # grew beyond a few thousand entries.
        from lca.contracts.models.observability.journal import ToolInvoked

        for stamped in reversed(self._events):
            event = stamped.event
            if isinstance(event, ToolInvoked) and event.idempotency_key == idempotency_key:
                return event
        return None

    def get_blob(self, seq: int) -> bytes | None:
        """O(1) serialized blob for the event payload (PR2 / §7.4).

        Returns the JSON-serialized event payload or None if seq is out of
        range.  Used by projectors that need the raw form without a dataclass
        reconstruction.
        """
        stamped = self.get(seq)
        if stamped is None:
            return None
        import dataclasses
        import json

        return json.dumps(dataclasses.asdict(stamped.event), ensure_ascii=False).encode("utf-8")

    def derive_events(
        self,
        predicate: Callable[[StampedEvent], bool],
    ) -> tuple[StampedEvent, ...]:
        """增量投影：从日志投影出满足 predicate 的子集。

        首次调用全量扫描，后续 append 后失效并增量扩展（只扫描新事件）。
        缓存按 predicate 的 id 分桶——同一 predicate 对象复用缓存。

        设计来源：DSH Session.deriveMessages() 增量缓存。
        """
        pid = id(predicate)
        cached = self._projection_cache.get(pid)
        if cached is not None:
            result, last_seq = cached
            # 增量扩展：只扫描 last_seq 之后的新事件
            for event in self._events:
                if event.seq > last_seq and predicate(event):
                    result.append(event)
            cached = (result, self._seq)
            self._projection_cache[pid] = cached
            return tuple(result)
        # 首次全量扫描
        result = [e for e in self._events if predicate(e)]
        self._projection_cache[pid] = (result, self._seq)
        return tuple(result)

    def flush(self) -> None:
        self._resolve_subscribers_if_needed()
        for subscriber in self._subscribers:
            subscriber.flush()

    def close(self) -> None:
        self._resolve_subscribers_if_needed()
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
