"""EventBus —— ADR-0183 §3.1。

LCA 事件总线唯一入口。旧 EventMechanism 保留兼容(14 天过渡),EventBus 是新 SSOT。

不变量:
- I-FW-BUS-1: publish 是 producer 唯一入口;subscribers 是 consumer 唯一入口
- I-FW-BUS-2: 失败语义由 failure= 参数决定,不是入口区分
- I-FW-BUS-3: 自定义逻辑只通过 Pipeline + 4 hook Protocol + SinkBackend

设计要点:
- EventBus 进程级单例(EventBus.default())
- pipeline 可热装载(register_pipeline),装载前 publish 走"无 pipeline"路径
- pre_dispatch hook chain 在校验 schema 之前(spec validation 在 hook 之后)
- trace_id 优先 payload.trace_id → contextvars → new_id("trc")(PR-12 才会启用
  contextvars,本 PR 留 stub)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.event import Category, EventPayload
from lca_kernel.events.errors import (
    EventMechanismError,
    MissingPluginIdentityError,
    UnauthorizedPublishError,
    UnauthorizedSubscribeError,
)
from lca_kernel.events.hooks import (
    ConsumerResult,
    FailureAction,
    PostDispatchHook,
    PreDispatchHook,
    PublishContext,
    SkipDispatch,
)
from lca_kernel.events.mechanism import EventRef
from lca_kernel.events.registry import EventRegistry, EventSpec

_log = logging.getLogger(__name__)

P = TypeVar("P", bound=EventPayload)


# ── 公开枚举 / 错误 ──────────────────────────────────────────────────────


class FailureSemantics(str, Enum):
    """consumer 失败语义(sink vs subscriber)。"""

    FAIL_FAST = "fail_fast"
    CONTAINED = "contained"


class PayloadSchemaError(EventMechanismError):
    """payload 与 spec 不符(ADR-0183 §3.1 step 4)。

    在 lca_kernel.events.errors 已有 EventMechanismError 基类;本类作为最小
    占位,本 PR 不修改 errors.py(PR-3 同步加入 errors)。
    """


# ── ConsumerHandle ───────────────────────────────────────────────────────


@dataclass
class ConsumerHandle:
    """subscribe() 返回句柄；unregister 留 stub(本 PR 框架不实装删除路径)。"""

    plugin: type
    category: Category
    unregister: Callable[[], None] = lambda: None


# ── EventBus 本体 ────────────────────────────────────────────────────────


class EventBus(Generic[P]):
    """LCA 事件总线唯一入口(ADR-0183 §3.1)。

    协议:
    - producer 调 publish(payload, *, producer=…)
    - consumer 调 subscribe(*, plugin, on_event, failure=…)
    - sink 走 subscribe(failure=FAIL_FAST)
    - subscriber 走 subscribe(failure=CONTAINED)

    自定义逻辑走 Pipeline 配置 + 4 hook Protocol。
    """

    _default_instance: EventBus[P] | None = None

    def __init__(self, registry: EventRegistry) -> None:
        self._registry = registry
        self._spec_by_category: dict[Category, EventSpec] = {
            spec.category: spec for spec in registry.specs
        }
        self._subscribers: dict[
            Category, list[tuple[type, Callable[[EventPayload, EventRef], None], FailureSemantics]]
        ] = defaultdict(list)
        self._pre_hooks: list[PreDispatchHook] = []
        self._post_hooks: list[PostDispatchHook] = []
        self._failure_hooks: list[
            Callable[[EventPayload, EventRef, BaseException], FailureAction]
        ] = []

    # ── 进程级单例 ────────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> EventBus[P]:
        # 推迟导入避免循环(bus 引用 mechanism,mechanism 不应 import bus)
        from lca_kernel.events.mechanism import EventMechanism

        if cls._default_instance is None:
            mechanism = EventMechanism.default()
            bus: EventBus[P] = cls(mechanism.registry)
            cls._default_instance = bus
        return cls._default_instance

    @classmethod
    def set_default(cls, instance: EventBus[P] | None) -> None:
        cls._default_instance = instance

    @classmethod
    def reset_singleton(cls) -> None:
        cls._default_instance = None

    # ── 公开面(ADR-0183 §3.1)───────────────────────────────────────────────

    def publish(
        self,
        payload: EventPayload,
        *,
        producer: type,
        trace_id: str | None = None,
    ) -> EventRef:
        """唯一发送入口。流程见 ADR-0183 §3.1 publish 流程 1–9。"""
        if producer is None or not isinstance(producer, type):
            raise MissingPluginIdentityError("publish")
        category = payload.category

        if not self._registry.can_publish(producer, category):
            raise UnauthorizedPublishError(producer.__qualname__, category.value)

        ctx = PublishContext(bus=self, producer=producer, ts=time.time(), trace_id=trace_id)

        effective = self._run_pre_dispatch(payload, producer, ctx)
        self._validate_schema(category, effective)

        effective_trace = trace_id or getattr(effective, "trace_id", None) or new_id("trc")
        ref = EventRef(
            event_id=new_id("evt"),
            category=category.value,
            trace_id=effective_trace,
            ts=ctx.ts,
        )

        results = self._fanout(effective, ref)
        self._run_post_dispatch(effective, ref, results)

        if any(r.exc is not None for r in results):
            self._run_failure_hooks(effective, ref, results)

        return ref

    def subscribe(
        self,
        *,
        plugin: type,
        category: Category | str,
        on_event: Callable[[EventPayload, EventRef], None],
        failure: FailureSemantics = FailureSemantics.CONTAINED,
    ) -> ConsumerHandle:
        """唯一消费入口。failure=FAIL_FAST 走 sink 路径(失败上抛);
        failure=CONTAINED 走 subscriber 路径(失败吞错)。

        鉴权用 registry.can_subscribe(EventMechanism 已有白名单;sink 复用
        subscribers 白名单,见 mechanism.py:140 注释)。
        """
        if plugin is None or not isinstance(plugin, type):
            raise MissingPluginIdentityError("subscribe")
        cat = self._coerce_category(category)
        if not self._registry.can_subscribe(plugin, cat):
            raise UnauthorizedSubscribeError(plugin.__qualname__, cat.value)
        self._subscribers[cat].append((plugin, on_event, failure))
        return ConsumerHandle(plugin=plugin, category=cat)

    def register_pipeline(self, pipeline: object) -> None:
        """装载声明式编排(Profile 启动时调用一次)。

        装载后 hook chain 即生效。pipeline 类型由 lca_kernel.events.pipeline
        定义,本方法在 TYPE_CHECKING 之外也直接 import(避免 Generic[P] 类型
        推导出问题),用 duck-type 取属性。
        """
        for spec in getattr(pipeline, "hooks", ()):
            inst = spec.hook()
            stage = spec.stage.value if hasattr(spec.stage, "value") else str(spec.stage)
            # Protocol 不带 @runtime_checkable → isinstance 不可用,改用 hasattr
            # duck-type 判别(接口稳定,见 hooks.py Protocol 定义)
            if stage == "pre_dispatch" and hasattr(inst, "before_publish"):
                self._pre_hooks.append(inst)
            elif stage == "post_dispatch" and hasattr(inst, "after_dispatch"):
                self._post_hooks.append(inst)
            elif stage == "on_failure":
                on_fail = getattr(inst, "on_consumer_failure", None)
                if callable(on_fail):
                    self._failure_hooks.append(on_fail)

    # ── 内部 ──────────────────────────────────────────────────────────────

    def _run_pre_dispatch(
        self,
        payload: EventPayload,
        producer: type,
        ctx: PublishContext,
    ) -> EventPayload:
        """跑 pre_dispatch hook chain;遇 SkipDispatch 抛 PayloadSchemaError。"""
        current: EventPayload = payload
        for hook in self._pre_hooks:
            result = hook.before_publish(current, producer, ctx)
            if isinstance(result, SkipDispatch):
                raise PayloadSchemaError(
                    f"pre_dispatch hook {type(hook).__qualname__} returned SkipDispatch"
                )
            if result is not None:
                current = result
        return current

    def _validate_schema(self, category: Category, payload: EventPayload) -> None:
        """spec validation:无 spec 则 skip;payload type 不符 → 抛 PayloadSchemaError。

        详细 spec.fields 校验推迟到 PR-3。
        """
        spec = self._spec_by_category.get(category)
        if spec is None:
            return
        expected_cls = spec.payload_class
        if not isinstance(payload, expected_cls):
            raise PayloadSchemaError(
                f"category={category.value} 期望 payload type "
                f"{expected_cls.__qualname__}, 实际 {type(payload).__qualname__}"
            )

    def _fanout(
        self,
        payload: EventPayload,
        ref: EventRef,
    ) -> list[ConsumerResult]:
        """fanout:FAIL_FAST 路径首个 sink 抛错上抛,CONTAINED 路径统一吞错。"""
        results: list[ConsumerResult] = []
        for plugin_cls, callback, failure in self._subscribers.get(payload.category, ()):
            try:
                callback(payload, ref)
                results.append(ConsumerResult(plugin=plugin_cls, category=payload.category))
            except Exception as exc:
                results.append(
                    ConsumerResult(
                        plugin=plugin_cls,
                        category=payload.category,
                        exc=exc,
                    )
                )
                if failure is FailureSemantics.FAIL_FAST:
                    # sink 路径:首个 sink 抛错上抛
                    raise
                _log.exception(
                    "consumer callback failed",
                    extra={"event_id": ref.event_id, "category": payload.category.value},
                )
        return results

    def _run_post_dispatch(
        self,
        payload: EventPayload,
        ref: EventRef,
        results: list[ConsumerResult],
    ) -> None:
        for hook in self._post_hooks:
            new_payloads = list(hook.after_dispatch(payload, ref, results))
            for np in new_payloads:
                # 派生事件:producer 取 hook 类型(框架内 hook,鉴权由 hook 自身承担)
                try:
                    self.publish(np, producer=type(hook))
                except Exception:
                    _log.exception(
                        "post_dispatch hook re-publish failed",
                        extra={"hook": type(hook).__qualname__},
                    )

    def _run_failure_hooks(
        self,
        payload: EventPayload,
        ref: EventRef,
        results: list[ConsumerResult],
    ) -> None:
        for hook in self._failure_hooks:
            for r in results:
                if r.exc is None:
                    continue
                try:
                    action = hook(payload, ref, r.exc)
                except Exception:
                    _log.exception(
                        "failure hook raised",
                        extra={"hook": getattr(hook, "__qualname__", repr(hook))},
                    )
                    continue
                if action is FailureAction.RETHROW:
                    raise r.exc

    @staticmethod
    def _coerce_category(category: Category | str) -> Category:
        return category if isinstance(category, Category) else Category(category)

    @property
    def registry(self) -> EventRegistry:
        return self._registry


__all__ = [
    "ConsumerHandle",
    "EventBus",
    "FailureSemantics",
    "PayloadSchemaError",
]
