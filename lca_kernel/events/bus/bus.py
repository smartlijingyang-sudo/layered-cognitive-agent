"""EnvelopeBus —— LCA 事件总线唯一入口(SSOT)。ADR-0183 §3.1 / ADR-0184。

不变量:
- I-FW-BUS-1: publish 是 producer 唯一入口;subscribe 是 consumer 唯一入口
- I-FW-BUS-2: 失败语义由 failure= 参数决定,不是入口区分
- I-FW-BUS-3: 自定义逻辑只通过 Pipeline + 4 hook Protocol + SinkBackend
- I-FW-BUS-4: 业务不订阅 event.bus.dispatch.*(自观察事件走内部路径)

设计要点:
- 进程级单例(EnvelopeBus.default());生产装配由 lca.events.bus manifest 的
  setup_bus 经 set_default 注入,default() 只在无装配时按 config 目录自建
- pipeline 可热装载(register_pipeline),装载前 publish 走"无 pipeline"路径
- pre_dispatch hook chain 在校验 schema 之前(spec validation 在 hook 之后)
- trace_id 解析链(ADR-0183 §3.9):显式参数 → payload.trace_id → ambient
  contextvars → new_id("trc");ambient 值由 webserver 请求入口 set/reset
- 自观察事件(ADR-0183 §3.10)走 _emit_self_observation 内部路径:不进鉴权
  矩阵、不重入 hook chain,结构上杜绝递归
- 投递回执与计数器(ADR-0184 D1/D2/D4):publish 返回的 EventRef 携带
  persisted / subscriber_count;按 category 的 published / persisted /
  delivered / dropped 四值计数器经 delivery_snapshot() 只读投影;
  零落盘策略经 configure_delivery_policy(strict=...) 切换
"""

from __future__ import annotations

import contextvars
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, cast

import structlog

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.event import Category, EventPayload, Plane
from lca_kernel.events.errors.errors import (
    EventMechanismError,
    EventNoSinkError,
    MissingPluginIdentityError,
    UnauthorizedPublishError,
    UnauthorizedSubscribeError,
)
from lca_kernel.events.hooks.hooks import (
    ConsumerResult,
    FailureAction,
    FailureSemantics,
    PostDispatchHook,
    PreDispatchHook,
    PublishContext,
    SkipDispatch,
)
from lca_kernel.events.payloads.payloads import (
    DISPATCH_SELF_OBSERVATION_CATEGORIES,
    MechanismDispatchEventPayload,
)
from lca_kernel.events.registry.registry import EventRegistry, EventSpec

if TYPE_CHECKING:
    from lca_kernel.events.sinks import SinkBackend

_log = logging.getLogger(__name__)
_delivery_log = structlog.get_logger(__name__)

P = TypeVar("P", bound=EventPayload)


# ── 投递回执(ADR-0184 D1)────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EnvelopeRef:
    """投递回执基类 —— 落盘与持久化层所需的 4 字段。

    字段契约:
    - ``event_id`` —— 机制分配的全局唯一 ID;
    - ``category`` —— payload.category 的字符串值(Category.value);
    - ``trace_id`` —— 解析链(ADR-0183 §3.9)后的最终 trace_id;
    - ``ts`` —— publish 入口取时刻的 epoch(float,秒)。

    ``spine.runtime.build_record`` 与 persistence 层按本类型标注:落盘只需要
    这 4 字段。投递事实(是否落盘、派发数)见 :class:`EventRef`。
    """

    event_id: str
    category: str
    trace_id: str
    ts: float


@dataclass(frozen=True, slots=True)
class EventRef(EnvelopeRef):
    """publish 返回的投递回执 —— EnvelopeRef + 两项投递事实(ADR-0184 D1)。

    - ``persisted`` —— S3 是否至少有一个 sink 后端写入成功;
    - ``subscriber_count`` —— S4 实际派发的 consumer 回调数。

    两者在 publish 返回前同步填齐,生产者读到的是本次投递的既成事实。
    Session 观察面收到同形回执:``lca.session.lifecycle.bind`` 由
    SessionEvent 合成 6 字段 EventRef 交给 observer 回调。
    """

    persisted: bool
    subscriber_count: int


# ── 投递策略(ADR-0184 D4)──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DeliveryPolicy:
    """零落盘投递策略(ADR-0184 I2)。

    ``strict=True``:持久 category 零挂载 sink → publish 抛
    :class:`EventNoSinkError`(fail-loud),事件不进入 ``_fanout``;
    ``strict=False``:降级为 ``dropped`` 计数 + error 日志,事件继续派发。
    """

    strict: bool


# ── ambient trace_id(ADR-0183 §3.9)─────────────────────────────────────

_current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lca_event_trace_id", default=None
)
"""当前上下文的 ambient trace_id。

由请求/任务入口(webserver lifespan_adapter)在边界 set、离开时 reset;
EnvelopeBus.publish 缺显式 trace_id 时回退到本值。
contextvars 随 asyncio Task / copy_context 隔离,跨请求不串。
"""


def set_trace_id(trace_id: str) -> contextvars.Token[str | None]:
    """设置当前上下文的 ambient trace_id;返回 token 供 reset_trace_id 恢复。"""
    return _current_trace_id.set(trace_id)


def reset_trace_id(token: contextvars.Token[str | None]) -> None:
    """用 set_trace_id 返回的 token 恢复 ambient trace_id。"""
    _current_trace_id.reset(token)


def current_trace_id() -> str | None:
    """读当前上下文的 ambient trace_id;未设置返回 None。"""
    return _current_trace_id.get()


# ── 公开错误 ─────────────────────────────────────────────────────────────


class PayloadSchemaError(EventMechanismError):
    """payload 与 spec 不符(ADR-0183 §3.1 step 4)。

    EventMechanismError 类名保留以兼容(详见 errors.py 顶部 docstring)。
    """


# ── ConsumerHandle ───────────────────────────────────────────────────────


@dataclass
class ConsumerHandle:
    """subscribe() 返回句柄。框架不提供退订路径:unregister 恒为 no-op 占位。"""

    plugin: type
    category: Category
    unregister: Callable[[], None] = lambda: None


# ── EnvelopeBus 本体 ─────────────────────────────────────────────────────


class EnvelopeBus(Generic[P]):
    """LCA 事件总线 —— producer / consumer / sink 的唯一入口(ADR-0183 §3.1)。

    协议:
    - producer 调 publish(payload, *, producer=…) 返回 :class:`EventRef`
    - consumer 调 subscribe(*, plugin, on_event, failure=…)
    - sink 走 subscribe(failure=FAIL_FAST) 或 :meth:`mount_sink`
    - subscriber 走 subscribe(failure=CONTAINED)
    - 自定义逻辑走 Pipeline 配置 + 4 hook Protocol

    生命周期(ADR-0184 §1):
        S1 ACCEPT  鉴权 + schema 校验
        S2 RECORD  构造回执(event_id / category / trace_id / ts)
        S3 PERSIST _dispatch_sinks 同步落盘
        S4 DELIVER _fanout 同步派发订阅者

    公开面:
    - :meth:`publish` —— producer 唯一入口
    - :meth:`subscribe` / :meth:`subscribe_self_observation` —— consumer 唯一入口
    - :meth:`mount_sink` —— 落盘后端装载
    - :meth:`register_pipeline` —— hook chain 装载
    - :meth:`delivery_snapshot` —— 投递计数器只读快照
    - :meth:`configure_delivery_policy` —— 零落盘策略
    - :attr:`registry` —— 只读 SSOT 引用
    """

    _default_instance: ClassVar[EnvelopeBus[Any] | None] = None

    def __init__(
        self,
        registry: EventRegistry,
    ) -> None:
        self._registry = registry
        self._spec_by_category: dict[Category, EventSpec] = {
            spec.category: spec for spec in registry.specs
        }
        # 投递计数器(ADR-0184 D2):按 category 累计四值
        # (published / persisted / delivered / dropped)。
        self._delivery_counts: defaultdict[str, dict[str, int]] = defaultdict(
            self._new_delivery_counts
        )
        # COMPAT(delete-when: ADR-0184 PR-C 合并且 live-run 验证通过,
        # tracking: ADR-0184 PR-C)
        # 生产 boot 走 register_pipeline_once(只装 hook,不挂 sink),持久
        # category 零 sink 是装配态事实;默认 strict=False 让它降级为
        # dropped 计数 + error 日志,而非 fail-loud 抛 EventNoSinkError。
        self._delivery_policy = DeliveryPolicy(strict=False)
        self._subscribers: dict[
            Category, list[tuple[type, Callable[[EventPayload, EventRef], None], FailureSemantics]]
        ] = defaultdict(list)
        self._pre_hooks: list[PreDispatchHook] = []
        self._post_hooks: list[PostDispatchHook] = []
        self._failure_hooks: list[
            Callable[[EventPayload, EventRef, BaseException], FailureAction]
        ] = []
        # 自观察事件消费表(ADR-0183 §3.10):按字符串 category 路由,独立于
        # _subscribers(I-FW-BUS-4 禁止业务订阅),不重入 publish(防递归)。
        # 仅框架观察方通过 subscribe_self_observation 注册。
        self._self_observers: dict[
            str, list[tuple[type, Callable[[MechanismDispatchEventPayload, EventRef], None]]]
        ] = defaultdict(list)
        # 已装载的落盘后端(ADR-0183 §3.4):register_pipeline 仅装 hook,生产装配安全;
        # sink 的装载走 mount_sink(由 pipeline_loader.apply_pipeline 调用),
        # publish 期经 _dispatch_sinks 派发(FD-1,先于 consumer FD-2)。
        self._sinks: dict[str, tuple[SinkBackend, FailureSemantics]] = {}

    @property
    def registry(self) -> EventRegistry:
        return self._registry

    # ── producer 入口 ───────────────────────────────────────────────────

    def publish(
        self,
        payload: EventPayload,
        *,
        producer: type | str,
        trace_id: str | None = None,
    ) -> EventRef:
        """producer 唯一入口 —— S1 鉴权 → S2 回执 → S3 落盘 → S4 派发。

        时序:
        1. S1 ``registry.can_publish`` 鉴权;
        2. S2 构造 :class:`EventRef`(event_id / category / trace_id / ts),
           trace_id 经 :meth:`_resolve_trace_id` 解析链确定并透传到
           ``SpineContext``;``published`` 计数在此累加;
        3. pre_dispatch hook chain 可替换 payload,随后跑 spec 校验 ——
           fanout 看到的是替换后的 payload;
        4. S3 :meth:`_dispatch_sinks` 同步落盘,S4 :meth:`_fanout` 同步派发;
        5. persisted / delivered / dropped 三值在 finally 内按投递事实累加,
           回执随后填齐 ``subscriber_count``;
        6. post_dispatch hook 与 failure hook 在回执填齐后运行。

        失败语义:producer 身份缺失抛 :class:`MissingPluginIdentityError`;
        未授权抛 :class:`UnauthorizedPublishError`;payload 与 spec 不符或
        pre_dispatch 返回 SkipDispatch 抛 :class:`PayloadSchemaError`;
        sink / consumer 的 FAIL_FAST 失败上抛,CONTAINED 失败吞错并计数。
        """
        producer_cls = self._coerce_producer(producer)
        if producer_cls is None:
            raise MissingPluginIdentityError(
                "publish" if producer is None else f"publish(producer={producer!r})"
            )
        category = payload.category

        if not self._registry.can_publish(producer_cls, category):
            identifier = producer_cls.__qualname__
            if isinstance(producer, str):
                identifier = f"id={producer!r}"
            raise UnauthorizedPublishError(identifier, category.value)

        # S2 —— 回执 4 字段;persisted / subscriber_count 由投递路径填齐
        ref = EventRef(
            event_id=new_id("evt"),
            category=category.value,
            trace_id=self._resolve_trace_id(trace_id, payload),
            ts=time.time(),
            persisted=False,
            subscriber_count=0,
        )

        # trace_id 透传到 SpineContext(ADR-0183 §3.9)。
        try:
            from lca.infrastructure.observability.spine.context.context import SpineContext

            SpineContext.set_trace_id(ref.trace_id)
        except ImportError:
            pass  # SpineContext 不可用时退回 None

        counts = self._delivery_counts[category.value]
        counts["published"] += 1

        ctx = PublishContext(bus=self, producer=producer_cls, ts=time.time(), trace_id=trace_id)
        effective = self._run_pre_dispatch(payload, producer_cls, ctx)
        self._validate_schema(category, effective)

        persisted = False
        results: list[ConsumerResult] = []
        try:
            # S3:空 sink 走 zero-sink 策略(见 _dispatch_sinks)。
            persisted = self._dispatch_sinks(effective, ref)
            ref = replace(ref, persisted=persisted)
            # S4:同步 fanout。
            self._fanout(effective, ref, results)
        finally:
            if persisted:
                counts["persisted"] += 1
            if results:
                counts["delivered"] += 1
            if not persisted or (not results and self._has_declared_subscribers(category)):
                counts["dropped"] += 1
        ref = replace(ref, subscriber_count=len(results))

        self._run_post_dispatch(effective, ref, results)

        if any(r.exc is not None for r in results):
            self._run_failure_hooks(effective, ref, results)

        return ref

    # ── 投递回执 / 计数器 / 策略(ADR-0184 D2/D4)──────────────────────────

    def delivery_snapshot(self) -> dict[str, dict[str, int]]:
        """按 category 的投递计数器快照(ADR-0184 D2)。

        返回 ``{category: {"published":…, "persisted":…, "delivered":…,
        "dropped":…}}`` 的拷贝:只含发生过 publish 的 category;调用方可
        自由读取聚合,写回不影响计数器。所有权:返回值归调用方。
        ``published`` 在 publish 入口累加;``persisted`` / ``delivered`` /
        ``dropped`` 由 _dispatch_sinks + _fanout 投递路径填充。
        ``dropped`` 定义 = 事件未落盘,或零派发且注册表为该 category
        声明了订阅者。
        """
        return {category: dict(counts) for category, counts in self._delivery_counts.items()}

    def configure_delivery_policy(self, *, strict: bool) -> None:
        """设置零落盘投递策略(ADR-0184 D4),立即对后续 publish 生效。

        ``strict=True``:持久 category 零挂载 sink 抛 :class:`EventNoSinkError`;
        ``strict=False``:降级为 ``dropped`` 计数 + error 日志。
        """
        self._delivery_policy = DeliveryPolicy(strict=strict)

    @property
    def delivery_policy(self) -> DeliveryPolicy:
        """当前投递策略(只读)。"""
        return self._delivery_policy

    # ── 内部 helpers ────────────────────────────────────────────────────

    @staticmethod
    def _new_delivery_counts() -> dict[str, int]:
        return {"published": 0, "persisted": 0, "delivered": 0, "dropped": 0}

    def _is_persistent_category(self, category: Category) -> bool:
        spec = self._spec_by_category.get(category)
        return spec is None or spec.plane is Plane.OBSERVABILITY

    @staticmethod
    def _resolve_trace_id(explicit: str | None, payload: EventPayload) -> str:
        return (
            explicit
            or getattr(payload, "trace_id", None)
            or _current_trace_id.get()
            or new_id("trc")
        )

    @staticmethod
    def _coerce_category(category: Category | str) -> Category:
        return category if isinstance(category, Category) else Category(category)

    def _coerce_producer(self, producer: type | str | None) -> type | None:
        if isinstance(producer, type):
            return producer
        if isinstance(producer, str):
            return self._registry.resolve_entity(producer)
        return None

    # ── 进程级单例 ────────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> EnvelopeBus[P]:
        if cls._default_instance is None:
            from pathlib import Path

            config_dir = Path(__file__).resolve().parent.parent / "config"
            registry = EventRegistry.load(config_dir)
            cls._default_instance = cls(registry)
        return cls._default_instance

    @classmethod
    def set_default(cls, instance: EnvelopeBus[P] | None) -> None:
        cls._default_instance = instance

    @classmethod
    def reset_singleton(cls) -> None:
        cls._default_instance = None

    def subscribe(
        self,
        *,
        plugin: type | str,
        category: Category | str,
        on_event: Callable[[EventPayload, EventRef], None],
        failure: FailureSemantics = FailureSemantics.CONTAINED,
    ) -> ConsumerHandle:
        """唯一消费入口。failure=FAIL_FAST 走 sink 路径(失败上抛);
        failure=CONTAINED 走 subscriber 路径(失败吞错)。

        ``plugin`` 可为 plugin ``type`` 或 plugin ``id`` 字符串（catalog 解析）。
        id 形态未在 catalog → 视为未授权。

        鉴权用 registry.can_subscribe（yaml subscribers 白名单装载时已物化
        进 ``subscribers`` 映射,sink 复用 subscribers 白名单）。
        """
        plugin_cls = self._coerce_producer(plugin)
        if plugin_cls is None:
            raise MissingPluginIdentityError(
                "subscribe" if plugin is None else f"subscribe(plugin={plugin!r})"
            )
        cat = self._coerce_category(category)
        if not self._registry.can_subscribe(plugin_cls, cat):
            identifier = plugin_cls.__qualname__
            if isinstance(plugin, str):
                identifier = f"id={plugin!r}"
            raise UnauthorizedSubscribeError(identifier, cat.value)
        self._subscribers[cat].append((plugin_cls, on_event, failure))
        return ConsumerHandle(plugin=plugin_cls, category=cat)

    def subscribe_self_observation(
        self,
        *,
        plugin: type,
        category: str,
        on_event: Callable[[MechanismDispatchEventPayload, EventRef], None],
    ) -> None:
        """框架自观察事件的唯一消费入口(§3.10)。

        I-FW-BUS-4:业务方不得订阅 ``event.bus.dispatch.*``;本入口仅供
        框架观察方(如自观察 sink)注册。自观察事件不在 Category 闭集与
        注册表白名单内,因此不走 registry 鉴权;category 必须在
        :data:`DISPATCH_SELF_OBSERVATION_CATEGORIES` 闭集内。
        """
        if plugin is None or not isinstance(plugin, type):
            raise MissingPluginIdentityError("subscribe_self_observation")
        if category not in DISPATCH_SELF_OBSERVATION_CATEGORIES:
            raise UnauthorizedSubscribeError(plugin.__qualname__, category)
        self._self_observers[category].append((plugin, on_event))

    def mount_sink(
        self,
        sink_id: str,
        backend: SinkBackend,
        *,
        failure: FailureSemantics = FailureSemantics.FAIL_FAST,
    ) -> None:
        """装载落盘后端(§3.4)。装载后 :meth:`publish` 经 ``_dispatch_sinks``
        把 ``build_record`` 结果派发到该后端。

        与 :meth:`register_pipeline` 分离的原因:生产 boot 走
        ``register_pipeline_once``(仅装 hook),避免迁移期与既有 ``FileSink``
        形成 ``<run_id>.spine.jsonl`` 双写者。完整声明式装配(含 sink)走
        ``lca.harness.profile.pipeline_loader.apply_pipeline``。

        ``failure`` 语义:``FAIL_FAST`` 后端 ``append`` 抛错上抛给发送方
        (事实链丢字节不可接受);``CONTAINED`` 记日志后继续。
        """
        self._sinks[sink_id] = (backend, failure)

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
                    self._failure_hooks.append(
                        cast(
                            "Callable[[EventPayload, EventRef, BaseException], FailureAction]",
                            on_fail,
                        )
                    )

    # ── 内部 ──────────────────────────────────────────────────────────────

    def _has_declared_subscribers(self, category: Category) -> bool:
        """注册表(含 consumer_rules 物化)是否为该 category 声明订阅者。"""
        return bool(self._registry.subscribers.get(category))

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

        只校验 payload 类型;spec.fields 的逐字段校验不在本路径。
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

    def _dispatch_sinks(self, payload: EventPayload, ref: EventRef) -> bool:
        """把事实派发到已装载的落盘后端(FD-1,先于 consumer FD-2)。

        每个后端收到 ``build_record(payload, ref)`` 的 10 键 ``SpineEventRecord``
        （含 ``trace_id``）;
        后端 ``append`` 抛错时按 :meth:`mount_sink` 声明的 ``failure`` 处理。
        返回 S3 持久回执:≥1 个后端写入成功为 True。

        零挂载策略(ADR-0184 I2):持久类 category 零 sink 时,
        ``strict=True`` 抛 :class:`EventNoSinkError`(事件不进 ``_fanout``);
        ``strict=False`` 记 error 日志后返回 False(事件继续派发),
        ``dropped`` 计数由 :meth:`publish` 统一记。非持久 category
        零 sink 只返回 False,不打 error 日志。
        """
        if not self._sinks:
            if self._is_persistent_category(payload.category):
                if self._delivery_policy.strict:
                    raise EventNoSinkError(payload.category.value)
                _delivery_log.error(
                    "persistent category dispatched with zero sinks; dropped",
                    category=payload.category.value,
                    event_id=ref.event_id,
                    trace_id=ref.trace_id,
                )
            return False
        # 延迟导入避免环:spine_runtime 依赖 mechanism,不与 bus 互引。
        from lca_kernel.events.spine.runtime import build_record

        record = build_record(payload, ref)
        persisted = False
        for sink_id, (backend, failure) in self._sinks.items():
            try:
                backend.append(record)
                persisted = True
            except Exception:
                if failure is FailureSemantics.FAIL_FAST:
                    raise
                _log.exception(
                    "sink backend append failed (contained)",
                    extra={"sink_id": sink_id, "event_id": ref.event_id},
                )
        return persisted

    def _fanout(
        self,
        payload: EventPayload,
        ref: EventRef,
        out: list[ConsumerResult],
    ) -> None:
        """fanout:FAIL_FAST 路径首个 sink 抛错上抛,CONTAINED 路径统一吞错。

        每次派发尝试(无论成功或 contained 失败)向 ``out`` 追加一条
        ``ConsumerResult``;FAIL_FAST 抛错时 ``out`` 保留抛错前的部分事实,
        供 :meth:`publish` 的计数器与回执使用。
        """
        for plugin_cls, callback, failure in self._subscribers.get(payload.category, ()):
            try:
                callback(payload, ref)
                out.append(
                    ConsumerResult(plugin=plugin_cls, category=payload.category, failure=failure)
                )
            except Exception as exc:
                out.append(
                    ConsumerResult(
                        plugin=plugin_cls,
                        category=payload.category,
                        exc=exc,
                        failure=failure,
                    )
                )
                if failure is FailureSemantics.FAIL_FAST:
                    # sink 路径:首个 sink 抛错上抛
                    raise
                _log.exception(
                    "consumer callback failed",
                    extra={"event_id": ref.event_id, "category": payload.category.value},
                )

    def _run_post_dispatch(
        self,
        payload: EventPayload,
        ref: EventRef,
        results: list[ConsumerResult],
    ) -> None:
        for hook in self._post_hooks:
            new_payloads = list(hook.after_dispatch(payload, ref, results))
            for np in new_payloads:
                if isinstance(np, MechanismDispatchEventPayload):
                    # 自观察事件走内部路径:继承被观察事件 trace_id,
                    # 不重入 hook chain(防递归),不进业务订阅(I-FW-BUS-4)。
                    self._emit_self_observation(np, trace_id=ref.trace_id)
                    continue
                # 派生事件:producer 取 hook 类型(框架内 hook,鉴权由 hook 自身承担)
                try:
                    self.publish(np, producer=type(hook))
                except Exception:
                    _log.exception(
                        "post_dispatch hook re-publish failed",
                        extra={"hook": type(hook).__qualname__},
                    )

    def _emit_self_observation(
        self,
        payload: MechanismDispatchEventPayload,
        *,
        trace_id: str,
    ) -> EventRef:
        """自观察事件内部路径(§3.10):继承被观察事件 trace_id。

        结构性防递归守卫:本路径不跑 pre/post_dispatch hook、不进
        _fanout 业务订阅表、不再调 publish —— 自观察事件不可能再次
        触发 MechanismDispatchObserver。callback 失败 contained 吞错。

        回执事实:自观察事件不经 sink 落盘(persisted=False),
        subscriber_count = 实际派发的自观察 callback 数;不进投递计数器
        (其 category 不在 Category 闭集内)。
        """
        ref = EventRef(
            event_id=new_id("evt"),
            category=payload.category,
            trace_id=trace_id,
            ts=time.time(),
            persisted=False,
            subscriber_count=0,
        )
        dispatched = 0
        for _plugin_cls, callback in self._self_observers.get(payload.category, ()):
            dispatched += 1
            try:
                callback(payload, ref)
            except Exception:
                _log.exception(
                    "self-observation callback failed",
                    extra={"event_id": ref.event_id, "category": payload.category},
                )
        return replace(ref, subscriber_count=dispatched)

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


__all__ = [
    "ConsumerHandle",
    "ConsumerResult",
    "DeliveryPolicy",
    "EnvelopeBus",
    "EnvelopeRef",
    "EventRef",
    "FailureSemantics",
    "PayloadSchemaError",
    "current_trace_id",
    "reset_trace_id",
    "set_trace_id",
]
