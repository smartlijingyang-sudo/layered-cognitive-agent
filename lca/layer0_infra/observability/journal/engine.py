"""运行事件账本的单一追加入口。

``RunStore`` 只拥有四项职责：验证已登记的类型、在提交边界执行数据策略、分配
连续序列并追加不可变记录、在提交后通知投影注册表。查询、洞察、SSE、OTel 和
持久化均为独立投影，不在账本内维护第二份状态。

PR-8：append-only 存储委托给 ``JournalStoreBackend``；当前唯一实现是
``InMemoryJournalStore``，文件 backed / 远端实现由后续 PR 的 Plugin 落地。
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Sequence
from enum import Enum
from typing import Any

from lca.contracts.models.observability.event import EventAudience, EventSensitivity
from lca.contracts.models.observability.journal import (
    JournalEvent,
    RunScope,
    RuntimeObserved,
    StampedEvent,
    get_current_run_scope,
)
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES
from lca.contracts.observability.journal_store import JournalStoreBackend
from lca.layer0_infra.observability.event_catalog import descriptor_for
from lca.layer0_infra.observability.journal.backends.memory import InMemoryJournalStore
from lca.layer0_infra.observability.policy import AttributePolicy, redact_restricted
from lca.layer0_infra.observability.projection_registry import EventProjection, ProjectionRegistry


class UnregisteredJournalEventError(TypeError):
    """发射了未登记事件类型时拒绝写入。"""

    def __init__(self, event_type: type[JournalEvent]) -> None:
        known = ", ".join(sorted(JOURNAL_EVENT_CLASSES))
        super().__init__(f"未登记的运行事件 {event_type.__name__}；词表：{known}")


class RunStore:
    """一个 run 的 append-only 事件账本。

    账本的序列由提交顺序唯一决定，投影只能看到已提交事件。该类没有订阅器
    工厂、查询缓存、幂等缓存或派生状态；这些能力由各自的投影或执行策略提供。
    """

    def __init__(
        self,
        projections: Sequence[EventProjection] = (),
        *,
        policy: AttributePolicy | None = None,
        registry: ProjectionRegistry | None = None,
        backend: JournalStoreBackend | None = None,
    ) -> None:
        if registry is not None and projections:
            raise ValueError("RunStore accepts projections or registry, not both")
        self._policy = policy if policy is not None else AttributePolicy()
        self._backend: JournalStoreBackend = backend if backend is not None else InMemoryJournalStore()
        self._registry = registry if registry is not None else ProjectionRegistry(projections)

    @property
    def events(self) -> tuple[StampedEvent, ...]:
        """已提交事件的不可变快照。"""
        return tuple(self._backend.events())

    @property
    def seq(self) -> int:
        """最后一个已提交序列；空账本为零。"""
        return len(self._backend.events())

    @property
    def projections(self) -> tuple[EventProjection, ...]:
        """已装配的只读投影。"""
        return self._registry.projections

    def with_projection(self, projection: EventProjection) -> RunStore:
        """返回追加 ``projection`` 后的新 RunStore（原实例不变）。

        Boot 期构造的基线 journal 持有共享 readers（langfuse 等）；run 边
        追加 jsonl/tail/process_journal 等 run-scoped writer，生成新 RunStore
        挂到 ``BoundObservability`` 上，老 readers 仍然在原基线实例里。
        """
        return RunStore(
            projections=tuple(self._registry.projections) + (projection,),
            policy=self._policy,
        )

    @property
    def backend(self) -> JournalStoreBackend:
        """暴露当前 backend，便于测试与诊断。"""
        return self._backend

    def append(self, event: JournalEvent) -> StampedEvent:
        """验证、治理、提交，再向投影发布事件。

        事件必须是词表登记的 frozen dataclass。提交不等待并且不依赖任意投影；
        投影异常由注册表隔离，因此不会更改 Agent 的领域执行语义。
        """
        event_type = type(event)
        if event_type.__name__ not in JOURNAL_EVENT_CLASSES:
            raise UnregisteredJournalEventError(event_type)
        if not dataclasses.is_dataclass(event):
            raise TypeError(f"运行事件必须是 dataclass：{event_type.__name__}")
        params = getattr(event_type, "__dataclass_params__", None)
        if not getattr(params, "frozen", False):
            raise TypeError(f"运行事件必须是 frozen dataclass：{event_type.__name__}")

        sanitized = self._apply_policy(event)
        causation = sanitized.causation_refs if isinstance(sanitized, RuntimeObserved) else ()
        stamped = StampedEvent(
            seq=len(self._backend.events()) + 1,
            ts=time.time(),
            scope=get_current_run_scope() or RunScope(),
            event=sanitized,
            event_type=event_type.__name__,
            data=dataclasses.asdict(sanitized),
            parent_seq=causation[-1] if causation else None,
        )
        self._backend.append(stamped)
        self._registry.publish(stamped)
        return stamped

    def write(self, event: JournalEvent) -> StampedEvent | None:
        """JournalBackend 协议入口：append 的别名。"""
        return self.append(event)

    def get(self, seq: int) -> StampedEvent | None:
        """按连续序列 O(1) 读取一条已提交事件。"""
        return self._backend.get(seq)

    def read_from(self, after_seq: int) -> tuple[StampedEvent, ...]:
        """返回严格晚于 ``after_seq`` 的事件，供可恢复消费者拉取。"""
        return tuple(self._backend.read_from(after_seq))

    def flush(self) -> None:
        """请求可缓冲投影与后端提交其自身的输出。"""
        self._registry.flush()
        self._backend.flush()

    def close(self) -> None:
        """关闭投影与后端，不删除已提交账本。"""
        self._registry.close()
        self._backend.close()

    def _apply_policy(self, event: JournalEvent) -> JournalEvent:
        """在事件提交边界一次性规范化枚举、文本和运行解释属性。

        对 sensitivity=confidential 或 audience=restricted 的事件，所有字符串字段
        强制走 ``redact_restricted()``，覆盖 verbosity 档位（评估文档 §49、§67）。
        """
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


__all__ = ["RunStore", "UnregisteredJournalEventError"]
