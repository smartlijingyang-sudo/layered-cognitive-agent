"""4 个 hook Protocol + 默认实现 —— ADR-0183 §3.2。

plugin 通过实现 hook Protocol 注入自定义逻辑；Pipeline 装载时绑定 stage。

不变量（ADR-0183 §4）:
- I-FW-BUS-3: 自定义逻辑只能通过 Pipeline 编排 + 4 hook Protocol + SinkBackend
  协议注入；plugin 不允许 import EventBus 内部。
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from lca.contracts.event import Category, EventPayload
from lca_kernel.events.payloads import MechanismDispatchEventPayload

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventBus
    from lca_kernel.events.registry import EventSpec
    from lca_kernel.events.spine_runtime import EventRef

# ── 公开枚举 / 哨兵 ──────────────────────────────────────────────────────


class FailureSemantics(str, Enum):
    """consumer 失败语义(sink vs subscriber)。

    FAIL_FAST = sink 路径(失败上抛 publisher);CONTAINED = subscriber
    路径(失败吞错)。定义在 hooks 层因为 ConsumerResult 需要携带它供
    post_dispatch 观察;bus 模块 re-export 保持公开面不变。
    """

    FAIL_FAST = "fail_fast"
    CONTAINED = "contained"


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

    返回 0..N 新事件;空 Iterable = 无派生。路由由 bus 决定:
    - :class:`MechanismDispatchEventPayload` → bus 内部自观察路径
      (不重入 hook chain,防递归;I-FW-BUS-4)
    - 其他 EventPayload → bus.publish 再次进入总线
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
    """publish 显式传入的 trace_id;ambient contextvars 回退由
    EventBus._resolve_trace_id 统一解析,hook 不重复实现。"""


@dataclass(frozen=True, slots=True)
class ConsumerResult:
    """单个 consumer 的执行结果,供 post_dispatch / failure hook 观察。"""

    plugin: type
    category: Category
    exc: BaseException | None = None
    """不为空即失败。"""
    failure: FailureSemantics = FailureSemantics.CONTAINED
    """该 consumer 的失败语义;自观察据此区分 sinks(FAIL_FAST)/consumers(CONTAINED)。"""

    @property
    def failed(self) -> bool:
        return self.exc is not None


# ── 默认实现 ────────────────────────────────────────────────────────────


class TraceContextHook:
    """PreDispatchHook：trace_id seam,保持 payload 透传。

    trace_id 解析由 :meth:`EventBus._resolve_trace_id` 单点承担
    (显式参数 → payload.trace_id → ambient contextvars → new_id);
    EventPayload 是 frozen + extra=forbid 的 pydantic 模型,hook 无法
    泛化写入 trace_id 字段,因此本 hook 不重复实现解析,仅作为
    Pipeline 装载的 pre_dispatch seam 存在(未来按类型注入扩展点)。
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
    """PostDispatchHook：机制自指派观察(ADR-0183 §3.10)。

    dispatch 完成后,按失败语义把 results 拆成两个阶段并派生自观察事件:
    - ``event.bus.dispatch.sinks.end`` ← FAIL_FAST(sink)结果
    - ``event.bus.dispatch.consumers.end`` ← CONTAINED(subscriber)结果

    仅当该阶段有实际执行的 consumer 时才派生(不空发)。派生的
    :class:`MechanismDispatchEventPayload` 由 bus 走内部自观察路径
    (不重入 post_dispatch,防递归;I-FW-BUS-4 禁止业务订阅)。

    ``duration_s`` 取整次 dispatch 的墙钟耗时(``time.time() - ref.ts``);
    bus 不做逐 consumer 计时,两阶段事件共用同一总耗时。
    """

    def after_dispatch(
        self,
        payload: EventPayload,
        ref: EventRef,
        results: list[ConsumerResult],
    ) -> Iterable[EventPayload]:
        duration_s = max(0.0, time.time() - ref.ts)
        for stage, semantics in (
            ("sinks", FailureSemantics.FAIL_FAST),
            ("consumers", FailureSemantics.CONTAINED),
        ):
            stage_results = [r for r in results if r.failure is semantics]
            if not stage_results:
                continue
            yield MechanismDispatchEventPayload(
                category=f"event.bus.dispatch.{stage}.end",
                consumer_count=len(stage_results),
                duration_s=duration_s,
                contained_failures=tuple(
                    type(r.exc).__qualname__ for r in stage_results if r.failed
                ),
            )


__all__ = [
    "ConsumerResult",
    "DefaultFailureHook",
    "FailureAction",
    "FailureHook",
    "FailureSemantics",
    "MechanismDispatchObserver",
    "PayloadSchemaHook",
    "PostDispatchHook",
    "PreDispatchHook",
    "PublishContext",
    "SkipDispatch",
    "SpecResolverHook",
    "TraceContextHook",
]
