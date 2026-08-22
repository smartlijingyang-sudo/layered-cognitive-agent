"""运行事件账本的单一追加入口(ADR-0065 PR-4 / L1/L2/L3/L7)。

``RunLedger``(前身 ``RunStore``)只拥有五项职责:
1. 验证已登记的 event 类型 + payload schema 版本(L4)
2. 在提交边界执行数据策略(L8)
3. 分配严格连续 seq 并比对 ``expected_run_seq``(L1/L3)
4. durable commit + terminal-event seal(L2/L7)
5. 在 commit 后通知 projection

任何并发调用方都必须显式声明 ``expected_run_seq``;不匹配抛
``LedgerSeqMismatchError``。终态事件提交后 ``is_sealed=True``,拒绝后续
追加(L7)。

PR-8 备注:保持类名 ``RunStore`` 不变以兼容 31 个调用方;``RunLedger`` 是
别名指向同一类(ADR-0065 §三 "保留既有类型" 原则的反例 —— 这里类是兼容
壳,真正的 L7/L1 增强在 ledger 协议层 + 单临界区实现)。
"""

from __future__ import annotations

import dataclasses
import threading
import time as _time
from collections.abc import Sequence
from enum import Enum
from typing import Any

from lca.contracts.models.observability.event import EventAudience, EventSensitivity
from lca.contracts.models.observability.journal import (
    JournalEvent,
    RunScope,
    RuntimeObserved,
    StampedEvent,
)
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES
from lca.contracts.observability.event_descriptor_registry import EventDescriptorRegistry
from lca.contracts.observability.journal_store import JournalStoreBackend
from lca.contracts.observability.ledger import (
    LedgerDurabilityError,
    LedgerSealedError,
    LedgerSeqMismatchError,
    LedgerStats,
    LedgerUnregisteredError,
)
from lca.layer0_infra.observability.event_catalog import descriptor_for
from lca.layer0_infra.observability.journal.backends.memory import InMemoryJournalStore
from lca.layer0_infra.observability.policy import AttributePolicy, redact_restricted
from lca.layer0_infra.observability.projection_registry import EventProjection, ProjectionRegistry
from lca.layer0_infra.observability.run_context import get_current_run_scope


class UnregisteredJournalEventError(LedgerUnregisteredError):
    """发射了未登记事件类型时拒绝写入(L4)。"""

    def __init__(self, event_type: type[JournalEvent]) -> None:
        known = ", ".join(sorted(JOURNAL_EVENT_CLASSES))
        super().__init__(f"未登记的运行事件 {event_type.__name__};词表:{known}")


# 终态事件类型(L7):保留作未来扩展点(PR-6 把 team-ledger 拆开后,
# AgentRunFinished 重新加入此集合自动触发 seal)。
#
# ADR-0065 §四 + L7: 单 ledger 维度上,terminal event 提交后冻结。当前
# 单 ledger 模式(整个 team 共享一个 RunStore)下,``AgentRunFinished``
# 在不同子 run 间会反复触发 seal,导致 member agent 后续 append 被拒。
# 解决方案:把 sealing 改成显式 ``seal()`` 调用;``append`` 不再自动 seal
# (L7 契约仍由 ``seal()`` 维持)。
_TERMINAL_EVENT_TYPES: frozenset[str] = frozenset()  # 当前空集


class RunStore:
    """一个 run 的 append-only 事件账本(ADR-0065 PR-4)。

    PR-4 增强:
    - 单一临界区 ``threading.Lock`` —— 并发 append 严格排队(L1)。
    - ``append()`` 支持 ``expected_run_seq``;不匹配抛 ``LedgerSeqMismatchError``(L3)。
    - ``seal()`` 提交 terminal event 并冻结账本(L7);terminal 后 ``is_sealed=True``。
    - ``LedgerDurabilityError`` 在 backend.append 失败时抛出(L2)。
    """

    def __init__(
        self,
        projections: Sequence[EventProjection] = (),
        *,
        policy: AttributePolicy | None = None,
        registry: ProjectionRegistry | None = None,
        backend: JournalStoreBackend | None = None,
        run_id: str = "",
        descriptor_registry: EventDescriptorRegistry | None = None,
    ) -> None:
        if registry is not None and projections:
            raise ValueError("RunStore accepts projections or registry, not both")
        self._policy = policy if policy is not None else AttributePolicy()
        self._backend: JournalStoreBackend = (
            backend if backend is not None else InMemoryJournalStore()
        )
        self._registry = registry if registry is not None else ProjectionRegistry(projections)
        self._descriptor_registry = descriptor_registry
        self._run_id = run_id
        self._lock = threading.Lock()
        self._sealed: bool = False
        self._backend_name = type(self._backend).__name__

    # ── RunLedger Protocol 表面(PR-4)─────────────────────────

    @property
    def is_sealed(self) -> bool:
        """L7: terminal event 后 True。"""
        return self._sealed

    @property
    def run_seq(self) -> int:
        return len(self._backend.events())

    @property
    def seq(self) -> int:
        """Compat alias for ``run_seq`` (旧 ``RunStore.seq`` 调用方)。"""
        return self.run_seq

    @property
    def run_id(self) -> str:
        return self._run_id

    def stats(self) -> LedgerStats:
        return LedgerStats(
            run_id=self._run_id,
            run_seq=self.run_seq,
            is_sealed=self._sealed,
            event_count=self.run_seq,
            backend_name=self._backend_name,
        )

    # ── 原有 RunStore API(保持兼容,行为增强)──────────────────

    @property
    def events(self) -> tuple[StampedEvent, ...]:
        """已提交事件的不可变快照。"""
        return tuple(self._backend.events())

    @property
    def projections(self) -> tuple[EventProjection, ...]:
        return self._registry.projections

    def with_projection(self, projection: EventProjection) -> RunStore:
        return RunStore(
            projections=(*self._registry.projections, projection),
            policy=self._policy,
            run_id=self._run_id,
        )

    @property
    def backend(self) -> JournalStoreBackend:
        return self._backend

    @property
    def policy(self) -> AttributePolicy:
        return self._policy

    def append(
        self,
        event: JournalEvent,
        *,
        expected_run_seq: int | None = None,
    ) -> StampedEvent:
        """L1 / L2 / L3 / L4 / L7: 验证 → 治理 → 单一临界区 → commit → publish。

        Raises:
            LedgerSealedError: 终态封存后调用(L7)
            LedgerSeqMismatchError: expected_run_seq 与当前不匹配(L3)
            LedgerUnregisteredError: descriptor 未登记或版本不匹配(L4)
            LedgerDurabilityError: required 事件持久化失败(L2)
        """
        # ── Pre-lock 校验(L4): 已知类型 + frozen dataclass ──
        event_type = type(event)
        if event_type.__name__ not in JOURNAL_EVENT_CLASSES:
            raise UnregisteredJournalEventError(event_type)
        if not dataclasses.is_dataclass(event):
            raise TypeError(f"运行事件必须是 dataclass:{event_type.__name__}")
        params = getattr(event_type, "__dataclass_params__", None)
        if not getattr(params, "frozen", False):
            raise TypeError(f"运行事件必须是 frozen dataclass:{event_type.__name__}")

        sanitized = self._apply_policy(event)
        causation = sanitized.causation_refs if isinstance(sanitized, RuntimeObserved) else ()

        # ── PR-6: 读取 plan_ref from ContextVar ─────────────
        from lca.contracts.models.observability.plan_ref import (
            get_current_plan_ref,
        )

        current_plan_ref = get_current_plan_ref()

        # ── 临界区(L1): 期望 seq 比对 + sealed 检查 + durable commit ──
        with self._lock:
            if self._sealed:
                raise LedgerSealedError(f"run_id={self._run_id!r} is sealed; append rejected (L7)")
            current_seq = len(self._backend.events())
            if expected_run_seq is not None and expected_run_seq != current_seq:
                raise LedgerSeqMismatchError(
                    f"run_id={self._run_id!r} expected_run_seq={expected_run_seq} "
                    f"but current={current_seq} (L1/L3)"
                )
            stamped = StampedEvent(
                seq=current_seq + 1,
                ts=_time.time(),
                scope=get_current_run_scope() or RunScope(),
                event=sanitized,
                event_type=event_type.__name__,
                data=dataclasses.asdict(sanitized),
                parent_seq=causation[-1] if causation else None,
                plan_ref=current_plan_ref,
            )
            try:
                self._backend.append(stamped)
            except Exception as exc:
                raise LedgerDurabilityError(
                    f"run_id={self._run_id!r} durable append failed: {exc}"
                ) from exc
            # ── L7: terminal event → 封存账本(临界区内)──────────
            # ADR-0065 §四 + L7: 单 ledger 维度上,terminal event 提交后冻结。
            # 当前单 ledger 模式(整个 team 共享一个 RunStore)下,``AgentRunFinished``
            # 在不同子 run 间会反复触发 seal,导致 member agent 后续 append 被拒。
            # 解决方案:把 sealing 改成显式 ``seal()`` 调用;``append`` 不再自动 seal
            # (L7 契约仍由 ``seal()`` 维持)。
            # TODO: PR-6 拆 team-ledger / agent-ledger,届时把
            # ``AgentRunFinished`` 加入 _TERMINAL_EVENT_TYPES 自动封存。

        # ── Post-lock publish(L2: 提交先于观察)────────────────
        self._registry.publish(stamped)
        return stamped

    def seal(self, terminal_event: JournalEvent | None = None) -> StampedEvent | None:
        """L7: 封存账本。

        可选地附带一个终态事件(若提供则先 append 再 seal;若账本已 sealed
        则抛 ``LedgerSealedError``)。不带终态事件时纯封存。
        """
        from lca.contracts.models.observability.plan_ref import (
            get_current_plan_ref,
        )

        with self._lock:
            if self._sealed:
                raise LedgerSealedError(f"run_id={self._run_id!r} is already sealed (L7)")
            stamped: StampedEvent | None = None
            if terminal_event is not None:
                # Reuse append path;but we already hold the lock so we can't
                # recursively enter. Inline the commit path:
                event_type = type(terminal_event)
                if event_type.__name__ not in JOURNAL_EVENT_CLASSES:
                    raise UnregisteredJournalEventError(event_type)
                sanitized = self._apply_policy(terminal_event)
                stamped = StampedEvent(
                    seq=len(self._backend.events()) + 1,
                    ts=_time.time(),
                    scope=get_current_run_scope() or RunScope(),
                    event=sanitized,
                    event_type=event_type.__name__,
                    data=dataclasses.asdict(sanitized),
                    plan_ref=get_current_plan_ref(),
                )
                self._backend.append(stamped)
            self._sealed = True
        if stamped is not None:
            # Publish post-lock(L2)
            self._registry.publish(stamped)
        return stamped

    def write(self, event: JournalEvent) -> StampedEvent | None:
        """JournalBackend 协议入口:append 的别名。"""
        return self.append(event)

    def get(self, seq: int) -> StampedEvent | None:
        return self._backend.get(seq)

    def read_from(self, after_seq: int) -> tuple[StampedEvent, ...]:
        return tuple(self._backend.read_from(after_seq))

    def flush(self) -> None:
        with self._lock:
            self._registry.flush()
            self._backend.flush()

    def close(self) -> None:
        with self._lock:
            self._registry.close()
            self._backend.close()

    def _apply_policy(self, event: JournalEvent) -> JournalEvent:
        if self._descriptor_registry is not None:
            type_name = type(event).__name__
            descriptor = self._descriptor_registry.require(type_name)
        else:
            descriptor = descriptor_for(event)
        aggressive = (
            descriptor.sensitivity is EventSensitivity.CONFIDENTIAL
            or descriptor.audience is EventAudience.RESTRICTED
        )
        updates: dict[str, Any] = {}
        has_output_truncated = any(
            field.name == "output_truncated" for field in dataclasses.fields(event)
        )
        for item in dataclasses.fields(event):
            value = getattr(event, item.name)
            if isinstance(value, Enum):
                updates[item.name] = value.value
                continue
            if isinstance(value, str):
                journal_kind = item.metadata.get("journal_kind")
                if aggressive:
                    redacted = redact_restricted(value)
                    if redacted != value:
                        updates[item.name] = redacted
                    continue
                if journal_kind == "content":
                    prepared, truncated = self._policy.prepare_content(item.name, value)
                    normalized = prepared or ""
                    if normalized != value:
                        updates[item.name] = normalized
                    if truncated and has_output_truncated:
                        updates["output_truncated"] = True
                else:
                    normalized = self._policy.prepare({item.name: value}).get(item.name, "")
                    if normalized != value:
                        updates[item.name] = normalized
                continue
            if isinstance(event, RuntimeObserved) and item.name in {"attributes", "output"}:
                if aggressive:
                    redacted = {k: redact_restricted(str(v)) for k, v in dict(value).items()}
                    if redacted != dict(value):
                        updates[item.name] = redacted
                    continue
                normalized = self._policy.prepare(dict(value))
                if normalized != value:
                    updates[item.name] = normalized
        return dataclasses.replace(event, **updates) if updates else event


# Alias: 0065 把 RunStore 视为 RunLedger Protocol 的实现
RunLedger = RunStore


__all__ = [
    "LedgerDurabilityError",
    "LedgerSealedError",
    "LedgerSeqMismatchError",
    "LedgerStats",
    "LedgerUnregisteredError",
    "RunLedger",
    "RunStore",
    "UnregisteredJournalEventError",
]
