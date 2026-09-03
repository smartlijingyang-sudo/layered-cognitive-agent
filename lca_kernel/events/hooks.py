"""4 个 hook Protocol + 默认实现 —— ADR-0183 §3.2。

plugin 通过实现 hook Protocol 注入自定义逻辑；Pipeline 装载时绑定 stage。

不变量（ADR-0183 §4）:
- I-FW-BUS-3: 自定义逻辑只能通过 Pipeline 编排 + 4 hook Protocol + SinkBackend
  协议注入；plugin 不允许 import EventBus 内部。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from lca.contracts.event import Category, EventPayload

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventBus
    from lca_kernel.events.registry import EventSpec
    from lca_kernel.events.spine_runtime import EventRef

# ── 公开枚举 / 哨兵 ──────────────────────────────────────────────────────


class FailureAction(str, Enum):
    """FailureHook 决定如何处置 consumer 抛出的异常。

    - CONTAIN: 吞错,记日志,继续走 post_dispatch 链(默认)
    - RETHROW: 上抛给 publish 调用方(fail-fast 路径)
    """

    CONTAIN = "contain"
    RETHROW = "rethrow"


class SkipDispatch:
    """PreDispatchHook 哨兵：返回它 → publish 跳过本事件,不发、不落盘。"""


# ── 公开 Protocol ────────────────────────────────────────────────────────


class PreDispatchHook(Protocol):
    """publish() 入口处:plugin 可改 payload / 校验 / 注入 context。

    返回 None 继续；返回 SkipDispatch → 跳过本事件；返回新 EventPayload
    → 替换原 payload(替换后再走后续 hook + schema 校验)。
    """

    def before_publish(
        self,
        payload: EventPayload,
        producer: type,
        ctx: PublishContext,
    ) -> EventPayload | SkipDispatch: ...


class SpecResolverHook(Protocol):
    """机制找不到 spec 时,plugin 可提供；返回 EventSpec 即注册。"""

    def resolve_spec(self, category: Category) -> EventSpec | None: ...


class PostDispatchHook(Protocol):
    """dispatch 完成后(所有 consumer 跑完),plugin 可派生事件 / 跨 EP 关联。

    返回 0..N 新事件 → 走 bus.publish 再次进入总线。空 Iterable = 无派生。
    """

    def after_dispatch(
        self,
        payload: EventPayload,
        ref: EventRef,
        results: list[ConsumerResult],
    ) -> Iterable[EventPayload]: ...


class FailureHook(Protocol):
    """consumer 抛错时,plugin 可补偿 / 改 failure semantics / 写自定义 metric。"""

    def on_consumer_failure(
        self,
        payload: EventPayload,
        ref: EventRef,
        exc: BaseException,
    ) -> FailureAction: ...


# ── 公开 dataclass ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PublishContext:
    """publish 阶段的不可变上下文,沿 hook chain 传递。"""

    bus: EventBus
    producer: type
    ts: float
    trace_id: str | None = None
    """trace_id 由 hook 注入,本 PR 留 stub —— PR-12 启用 contextvars。"""


@dataclass(frozen=True, slots=True)
class ConsumerResult:
    """单个 consumer 的执行结果,供 post_dispatch / failure hook 观察。"""

    plugin: type
    category: Category
    exc: BaseException | None = None
    """不为空即失败。"""

    @property
    def failed(self) -> bool:
        return self.exc is not None


# ── 默认实现（PR-2 落地,PR-12 启用）─────────────────────────────────────


class TraceContextHook:
    """PreDispatchHook：从 ctx 取 trace_id 注入 payload(本 PR 留 stub)。

    落地步骤:
    - 本 PR：method 直接返回 payload(stub)，保证 Pipeline 装载不抛。
    - PR-12：替换为 contextvars 取值 + 写 payload.trace_id。
    """

    def before_publish(
        self,
        payload: EventPayload,
        producer: type,
        ctx: PublishContext,
    ) -> EventPayload | SkipDispatch:
        return payload


class PayloadSchemaHook:
    """PreDispatchHook：失败时 raise PayloadSchemaError。

    校验逻辑由 EventBus.publish 调用 spec_for(category) 后委托本 hook;
    本类作为 marker,实装校验由 EventBus 在 hook chain 中执行(§3.1 step 4)。
    """

    def before_publish(
        self,
        payload: EventPayload,
        producer: type,
        ctx: PublishContext,
    ) -> EventPayload | SkipDispatch:
        return payload


class DefaultFailureHook:
    """FailureHook：默认吞错(FD-2 contained 语义)。"""

    def on_consumer_failure(
        self,
        payload: EventPayload,
        ref: EventRef,
        exc: BaseException,
    ) -> FailureAction:
        return FailureAction.CONTAIN


class MechanismDispatchObserver:
    """PostDispatchHook：自指派观察(本 PR 留 stub,等 PR-12)。

    PR-12 落地:
    - yield MechanismDispatchEventPayload(category=event.bus.dispatch.consumers.end, ...)
    - 默认 consumer_rules 不订阅 event.bus.dispatch.*(I-FW-BUS-4 守护)。
    """

    def after_dispatch(
        self,
        payload: EventPayload,
        ref: EventRef,
        results: list[ConsumerResult],
    ) -> Iterable[EventPayload]:
        return ()


__all__ = [
    "ConsumerResult",
    "DefaultFailureHook",
    "FailureAction",
    "FailureHook",
    "MechanismDispatchObserver",
    "PayloadSchemaHook",
    "PostDispatchHook",
    "PreDispatchHook",
    "PublishContext",
    "SkipDispatch",
    "SpecResolverHook",
    "TraceContextHook",
]
