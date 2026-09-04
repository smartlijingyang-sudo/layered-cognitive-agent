"""K5 观测装配 — 唯一 ``BoundObservability`` 装配点 + ObservabilityRuntime。

K5 在启动全景中的位置
====================

K1–K4(纯函数,无副作用)→  K3 cordis 启动(plugin fiber 灌入 backend registry)
                                          │
                                          └─→ K5 install_observability(本模块,装配点)
                                                │
                                                └─→ K6 yield 出去的 ctx 已带 Bound

观测属于 C7 横切面,只能由唯一入口装配;plugin 不允许自己 emit
``BootProfileResolved`` 之类的事件,也不允许绕过本模块直接构造
``BoundObservability``(ADR-0083 §2)。

Public surface
--------------
- :func:`install_observability` —— 把各 seam registry 装配成
  :class:`~lca.infrastructure.observability.facade.facade.BoundObservability`
  并挂到 :class:`cordis.Context` 的 ``"observability"`` 键(ADR-0083)。
- :class:`ObservabilityRuntime` —— ADR-0169 §D8 缝族 + CloseBarrier 装配
  入口;Profile 通过 :meth:`ObservabilityRuntime.from_profile` 一次性构造
  ``LoopCursorFactory / ProjectionHost / PersistenceCoordinator /
  CloseBarrier``(ADR-0169 §D8;ADR-0185 PR-4 后 capture 缝退场,
  model-visible 改由 ``ModelVisibleHook`` 走 spine event bus)。

Why a dedicated module
----------------------
原来 :mod:`lca.harness.profile.boot` 同时持有 ``_install_observability`` +
``_dispose_context`` + ``_boot_plugin`` + ``attach_profile_boot_products``,
违反 ADR-0083 §2 "可观测是横切观察" 收敛。拆出后 boot.py 只剩 cordis
Context + Fiber 启动;观测走 :func:`install_observability` 单入口,
``lca-ops diagnose plugin-tree`` 等诊断工具也能复用。

ADR-0169 增量(PR-25)
--------------------
本文件同时承载 ``ObservabilityRuntime`` —— 缝族架构(ADR-0169 D8)的
**唯一装配入口**。Runtime 是 ``frozen=True`` dataclass,持有缝族组件
引用;不持 cursor 实例(每次 :meth:`make_cursor` 派生新 cursor,
不同 run / 不同 step_id 互不污染)。

Profile 装配步骤(plan §Task 25):
    1. 读 profile 的 ``observability`` 段(plan_ref / projection_host 列表 /
       persistence 配置 / close_barrier 等);
    2. 构造 :class:`LoopCursorFactory`;
    3. 构造 :class:`StdProjectionHost`(带 default 初始 deriver 列表);
    4. 构造 :class:`StdCloseBarrier`(需要 Persistence / Host / Emitter);
    5. 把缝族 + factory 一起冻进 :class:`ObservabilityRuntime`。

ADR-0185 PR-4:原 capture 装配步已删除;model-visible 改由
``ModelVisibleHook`` 在 LLM adapter 边界走 spine event bus 统一注入,
Runtime 不再持有 capture 字段。

PersistenceCoordinator 不在 PR-25 装配范围 —— PR-15 已独立构造;
本 Runtime 接受外部注入的 persistence;为调用方便,``persistence=None``
fallback 到 :class:`NullPersistenceCoordinator`(ADR-0169 D8 barrier 注入面
不能为空;生产路径仍由调用方注入 FilePersistenceCoordinator)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.observability.close_barrier import CloseBarrier, CloseReason, CloseReport
from lca.harness.observability import assemble_observability
from lca.infrastructure.observability import (
    BoundObservability,
    NamedRegistry,
    ObservabilitySettings,
)

# PR-7:缝族实现由 registry 解析并实例化;kernel 不再持有具体类引用。
# 下列 import 仍保留在 docstring(:class:`Foo`)的引用中以便阅读,
# 但本模块运行时不再 import 它们 —— providers 注册它们,
# from_profile 通过 NamedRegistry.lookup 拿到的实例 duck-types
# 这些 Protocol / class。仓库 migration 完成时(rg from lca.infrastructure
# .observability.loop_cursor = 0)删除这些 impl 文件,本模块零修改。
__all__ = [
    "ObservabilityRuntime",
    "install_observability",
]


# PR-7:每个 seam 的默认 provider id;profile ``observability.X.implementation``
# 可显式覆盖。persistence 默认 = null(ADR-0169 D8 调用方注入面永不空);
# 其他缝默认 = standard(Std* 默认实现)。
_DEFAULT_PROVIDER_KEY: dict[str, str] = {
    "observability.loop_cursor": "standard",
    "observability.projection_host": "standard",
    "observability.close_barrier": "standard",
    "observability.persistence": "null",
}


def install_observability(ctx: Any) -> BoundObservability:
    """唯一 ``BoundObservability`` 装配点。

    把各 seam registry(``attribute_policy_backends`` / ``journal_backends`` /
    ``tracer_backends`` / ``fact_scorers``)装配成 ``BoundObservability``,
    通过 ``ctx.provide("observability", bound)`` 暴露给所有 plugin。

    Returns
    -------
    BoundObservability
        已绑定到 ``ctx`` 的对象;调用方可继续在 ``RunContext`` 上记录事件,
        但不能修改 backend 实例(backend 引用由 cordis Context 持有)。

    Notes
    -----
    装配顺序由 :func:`lca.harness.observability.assemble_observability` 控制
    (policy → readers → journal → tracer → scorers);该顺序保证 policy 先于
    journal / tracer 注入,fact_scorers 最后注入(它们消费已注入的 journal)。

    二次安装约定(ADR-0116 §决定 2)
    ------------------------------
    K3 内部会调本函数两次:第一次是 baseline(registry 仍为空,所有 backend
    为 no-op);plugin fiber spawn 完后再调一次,此时 registry 已被 plugin
    填入真实 backend,journal/tracer 真正可写。两次调用都安全。

    完整 K 链路地图见模块 docstring 的"K5 在启动全景中的位置"段。
    """
    return assemble_observability(
        ctx, ObservabilitySettings()
    )  # ↑ K5:装 BoundObservability;内部 ctx.provide("observability", bound)


@dataclass(frozen=True)
class ObservabilityRuntime:
    """缝族 + CloseBarrier 装配容器(ADR-0169 D8 / PR-25;ADR-0185 PR-4 capture 退场)。

    字段:
        cursor_factory  : LoopCursorFactory       —— 每次 make_cursor 派生新 cursor
        projection_host : StdProjectionHost       —— 默认注册清单(由 profile.initial 控制)
        persistence     : PersistenceCoordinator   —— 由调用方注入;本 Runtime 不构造
        barrier         : CloseBarrier            —— 协调 close 顺序

    ADR-0185 PR-4:原 capture 缝字段已删除;model-visible 改由
    ``ModelVisibleHook`` 在 LLM adapter 边界走 spine event bus 统一注入,
    Runtime 不再持有 capture 实例。

    Frozen:Runtime 装配后不可变;字段引用可换但不能原地改。与 ADR-0169
    G6 / L9 一致 —— 持有字段即 SSOT,projection 不再藏在 cursor 里。

    关闭流程(:meth:`close`)仅委托给 :attr:`barrier`(ADR-0169 D5):
        cursor.close(reason) → writable.iteration.closing EP
        → barrier.close(reason) → Persistence.flush → Host.flush_all → close EP emit
    """

    cursor_factory: Any  # PR-7:registry-resolved factory (LoopCursorFactory contract)
    projection_host: Any  # PR-7:registry-resolved ProjectionHost instance
    persistence: Any  # PersistenceCoordinator(protocol 位;由调用方注入)
    barrier: CloseBarrier
    plan_ref: str = "default"  # 从 profile 读;make_cursor 派生 Incarnation 用

    # ── 装配入口 ────────────────────────────────────────────────

    @classmethod
    def from_profile(
        cls,
        *,
        profile: Any,
        ctx: Any,
        persistence: Any = None,
    ) -> ObservabilityRuntime:
        """Profile → 缝族 + CloseBarrier 装配(ADR-0169 §D8 / PR-25 + PR-7)。

        Parameters
        ----------
        profile:
            Profile / ResolvedProfile / 任意 duck-typed 对象;读 ``plan_ref`` /
            ``observability`` 段(可缺省)。
        ctx:
            cordis Context,持有缝族 seam registry 提供的能力(PR-7 注入面)。
        persistence:
            :class:`PersistenceCoordinator` 实例;``None`` 时 fallback 到
            seam registry 里 ``observability.persistence['null']`` 提供的
            :class:`NullPersistenceCoordinator`(barrier 注入面永不空)。
            生产路径仍由调用方注入 :class:`FilePersistenceCoordinator`。

        Returns
        -------
        ObservabilityRuntime
            已 frozen 的缝族容器;调用方存到 ctx / ProfileBootProducts。

        Notes
        -----
        PR-7 改造:原硬编码 ``LoopCursorFactory()`` /
        ``StdProjectionHost(initial=...)`` /
        ``NullPersistenceCoordinator()`` / ``StdCloseBarrier(...)`` 改为
        从 ``ctx.inject("observability.<seam>")`` 拿到 NamedRegistry,
        按 ``profile.observability.<seam>.implementation``(缺省 = standard / null)
        选中 provider 的 factory。``from_profile`` 现在只读 profile 用于
        plan_ref / initial deriver 列表等**hints**;真正的
        实例化由 registry 完成。

        ADR-0185 PR-4:capture 缝删除后,装配不再 lookup
        ``observability.model_visible`` registry;model-visible 走
        ``ModelVisibleHook`` 在 LLM adapter 边界拦截,装配由
        ``events.model_visible.publisher`` plugin 完成。

        delete-when: ``rg "ObservabilityRuntime.from_profile" lca/ lca_kernel/ = 0``
        (transport 装配改走 capability 注入面后,本 wrapper 删除)
        """
        plan_ref = str(getattr(profile, "plan_ref", "default"))

        # ── 1) cursor factory —— registry lookup ──────────────────
        # The registry holds a callable that, when invoked with
        # (profile=, run_id=, trace_id=, spine=), returns (cursor, incarnation).
        # The standard provider registers ``LoopCursorFactory.from_profile``
        # (staticmethod) directly;replacement providers (test stub / null)
        # register their own callables with the same signature.
        cursor_key = _select_provider_key(profile, "loop_cursor", default="standard")
        cursor_registry = _require_registry(ctx, "observability.loop_cursor")
        cursor_factory = _lookup_provider(cursor_registry, cursor_key)

        # ── 2) projection host —— registry lookup,initial 作 key hint ──
        host_key = _select_provider_key(profile, "projection_host", default="standard")
        host_registry = _require_registry(ctx, "observability.projection_host")
        host_factory = _lookup_provider(host_registry, host_key)
        initial = _extract_projection_initial(profile)
        projection_host = host_factory(initial=initial or None)

        # ── 3) persistence —— 由调用方注入;None 时 fallback null provider ──
        resolved_persistence: Any = (
            persistence if persistence is not None else _instantiate_null_persistence(ctx)
        )

        # ── 4) close barrier —— registry lookup,collaborators 注入 ──
        barrier_key = _select_provider_key(profile, "close_barrier", default="standard")
        barrier_registry = _require_registry(ctx, "observability.close_barrier")
        barrier_factory = _lookup_provider(barrier_registry, barrier_key)
        barrier: CloseBarrier = barrier_factory(
            persistence=resolved_persistence,
            host=projection_host,
            close_emitter=_NullCloseEmitter(),
        )

        return cls(
            cursor_factory=cursor_factory,
            projection_host=projection_host,
            persistence=resolved_persistence,
            barrier=barrier,
            plan_ref=plan_ref,
        )

    # ── 派生 ────────────────────────────────────────────────────

    def make_cursor(
        self,
        *,
        run_id: str,
        trace_id: str,
        spine: Any,
    ) -> Any:
        """派生一个 :class:`LoopCursor`(默认实现 = StdLoopCursor)。

        spine 是 :class:`WritePort` 协议位(ADR-0169 D1 / L10);每次 run
        / 子代理派一个新 cursor;**不**复用 cursor 实例(ADR-0169 D6 / L14)。

        PR-7:``cursor_factory`` 是 NamedRegistry 提供的 callable(默认 =
        ``LoopCursorFactory.from_profile`` 静态方法),直接调用即可
        派生新 cursor。

        Returns
        -------
        StdLoopCursor
            cursor 实例;factory 同时返回 incarnation,本方法仅返回 cursor。
        """
        profile_proxy = type(
            "_ProfileProxy",
            (),
            {
                "plan_ref": self.plan_ref,
                "run_id": run_id,
            },
        )()
        cursor, _incarnation = self.cursor_factory(
            profile=profile_proxy,
            run_id=run_id,
            trace_id=trace_id,
            spine=spine,
        )
        return cursor

    # ── 关闭协同 ────────────────────────────────────────────────

    def close(self, reason: CloseReason) -> CloseReport:
        """Runtime close —— 委托给 :attr:`barrier`(ADR-0169 D5)。

        不直接调 cursor.close —— 业务路径在 cursor 上调 close 之前,Runtime
        已经隐式订阅了 ``writable.iteration.closing`` EP(PR-25 之后由 wiring
        注入);本方法提供「runtime 一次性收尾」的便捷入口。
        """
        return self.barrier.close(reason)


# ── 内部辅助 ────────────────────────────────────────────────


def _require_registry(ctx: Any, capability_key: str) -> NamedRegistry:
    """从 cordis Context 拿 seam registry;能力缺失时给清晰错误(PR-7)。"""
    if ctx is None:
        raise RuntimeError(
            f"{capability_key!r} seam registry not available: ctx is None; "
            "ObservabilityRuntime.from_profile requires a booted cordis Context "
            "with observability-default bundle loaded."
        )
    inject = getattr(ctx, "inject", None)
    if not callable(inject):
        raise RuntimeError(
            f"{capability_key!r} seam registry not available: ctx lacks inject(); "
            f"got {type(ctx).__name__}."
        )
    try:
        registry = inject(capability_key)
    except KeyError as exc:
        raise RuntimeError(
            f"{capability_key!r} seam registry not bound; "
            "profile must load observability-default bundle (PR-7)."
        ) from exc
    if not isinstance(registry, NamedRegistry):
        raise RuntimeError(
            f"{capability_key!r} seam registry has wrong type: "
            f"got {type(registry).__name__}, expected NamedRegistry."
        )
    return registry


def _select_provider_key(
    profile: Any,
    seam_short: str,
    *,
    default: str,
) -> str:
    """读 ``profile.observability.<seam>.implementation`` 选 provider id。"""
    section = getattr(profile, "observability", None)
    if section is None:
        return default
    if isinstance(section, dict):
        seam_section = section.get(seam_short) or {}
    else:
        seam_section = getattr(section, seam_short, None) or {}
    if isinstance(seam_section, dict):
        candidate = seam_section.get("implementation")
    else:
        candidate = getattr(seam_section, "implementation", None)
    if isinstance(candidate, str) and candidate:
        return candidate
    return default


def _lookup_provider(registry: NamedRegistry, key: str) -> Any:
    """从 NamedRegistry 查 provider factory;缺失时给清晰错误。"""
    factory = registry.get(key)
    if factory is None:
        available = sorted(registry.all().keys())
        raise RuntimeError(
            f"observability provider {key!r} not registered; available keys: {available}."
        )
    return factory


def _instantiate_null_persistence(ctx: Any) -> Any:
    """Resolve the null persistence factory through ``observability.persistence['null']``."""
    registry = _require_registry(ctx, "observability.persistence")
    factory = registry.get("null")
    if factory is None:
        # fallback to "default" alias;both null and standard providers register both keys
        factory = registry.get("default")
    if factory is None:
        raise RuntimeError(
            "observability.persistence seam has no null/default provider; "
            "load observability-default bundle."
        )
    import inspect

    if inspect.isclass(factory):
        return factory()
    return factory()


def _extract_projection_initial(profile: Any) -> list[Any]:
    """从 profile 读 ``observability.projection_host.initial`` 列表。

    PR-25 阶段:``initial`` 仅作 key hint 列表(profile 文本里写
    ``initial: [step_tree, narrative, graph, cost]``);真正的
    :class:`LoopProjectionDefinition` 装配由后续 PR 把 key → 实现映射
    完成(PR-18 ``register(key=...)`` API)。本阶段仅在 ``initial`` 元素
    是真正的 LoopProjectionDefinition 实例时透传;否则返回 ``[]``
    走 StdProjectionHost 的默认清单。
    """
    section = getattr(profile, "observability", None)
    if section is None:
        return []
    if isinstance(section, dict):
        host_section = section.get("projection_host") or {}
    else:
        host_section = getattr(section, "projection_host", None) or {}
    initial_raw = (
        host_section.get("initial")
        if isinstance(host_section, dict)
        else getattr(host_section, "initial", None)
    )
    if initial_raw is None:
        return []
    # 仅在元素是 LoopProjectionDefinition 实例时透传;str 列表视为 key hint
    # 当前走 default 注册清单
    from lca.contracts.observability.loop_projection import LoopProjectionDefinition

    return [item for item in initial_raw if isinstance(item, LoopProjectionDefinition)]


class _NullCloseEmitter:
    """PR-25 阶段 CloseBarrier.close_emitter 的占位实现。

    cursor.close(reason) 自身就是 close EP 的 emit 入口(ADR-0169 D5);
    barrier 不直接 emit close EP,仅协调 Persistence.flush / Host.flush_all
    顺序。``_NullCloseEmitter.emit_close`` 不写盘,仅占位;真实 cursor 在
    close() 时调 spine.append("writable.iteration.close", ...) 走真值流。
    """

    def emit_close(self, reason: CloseReason) -> None:  # pragma: no cover - 占位
        return None


__all__ = [
    "ObservabilityRuntime",
    "install_observability",
]
