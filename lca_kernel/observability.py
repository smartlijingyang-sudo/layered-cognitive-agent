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
- :class:`ObservabilityRuntime` —— ADR-0169 §D8 五缝 + CloseBarrier 装配
  入口;Profile 通过 :meth:`ObservabilityRuntime.from_profile` 一次性构造
  ``LoopCursorFactory / ProjectionHost / PersistenceCoordinator /
  ModelVisibleCapture / CloseBarrier`` 五件套(ADR-0169 §D8)。

Why a dedicated module
----------------------
原来 :mod:`lca.harness.profile.boot` 同时持有 ``_install_observability`` +
``_dispose_context`` + ``_boot_plugin`` + ``attach_profile_boot_products``,
违反 ADR-0083 §2 "可观测是横切观察" 收敛。拆出后 boot.py 只剩 cordis
Context + Fiber 启动;观测走 :func:`install_observability` 单入口,
``lca-ops diagnose plugin-tree`` 等诊断工具也能复用。

ADR-0169 增量(PR-25)
--------------------
本文件同时承载 ``ObservabilityRuntime`` —— 五缝架构(ADR-0169 D8)的
**唯一装配入口**。Runtime 是 ``frozen=True`` dataclass,持有五缝组件
引用;不持 cursor 实例(每次 :meth:`make_cursor` 派生新 cursor,
不同 run / 不同 step_id 互不污染)。

Profile 装配步骤(plan §Task 25):
    1. 读 profile 的 ``observability`` 段(plan_ref / projection_host 列表 /
       persistence 配置 / model_visible / close_barrier 等);
    2. 构造 :class:`LoopCursorFactory`;
    3. 构造 :class:`StdProjectionHost`(带 default 初始 deriver 列表);
    4. 构造 :class:`StdCloseBarrier`(需要 Persistence / Host / Emitter);
    5. 构造 :class:`StdModelVisibleCapture`(run_dir 来自 profile.runs_root);
    6. 把五件套 + factory 一起冻进 :class:`ObservabilityRuntime`。

PersistenceCoordinator 不在 PR-25 装配范围 —— PR-15 已独立构造;
本 Runtime 接受外部注入的 persistence(host 或 factory 持有即可)。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.contracts.observability.close_barrier import CloseBarrier, CloseReason, CloseReport
from lca.contracts.observability.model_visible_capture import (
    ModelVisibleCapture,
)
from lca.harness.observability import assemble_observability
from lca.infrastructure.observability import (
    BoundObservability,
    ObservabilitySettings,
)
from lca.infrastructure.observability.loop_cursor.close_barrier_impl import StdCloseBarrier
from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
from lca.infrastructure.observability.loop_cursor.model_visible_capture import (
    StdModelVisibleCapture,
)
from lca.infrastructure.observability.loop_cursor.projection_host import StdProjectionHost


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
    """五缝 + CloseBarrier 装配容器(ADR-0169 D8 / PR-25)。

    五缝:
        cursor_factory  : LoopCursorFactory       —— 每次 make_cursor 派生新 cursor
        projection_host : StdProjectionHost       —— 默认注册清单(由 profile.initial 控制)
        persistence     : PersistenceCoordinator   —— 由调用方注入;本 Runtime 不构造
        capture         : ModelVisibleCapture     —— LLM 边界 5 件套
        barrier         : CloseBarrier            —— 协调 5 步 close 顺序

    Frozen:Runtime 装配后不可变;字段引用可换但不能原地改。与 ADR-0169
    G6 / L9 一致 —— 持有字段即 SSOT,projection 不再藏在 cursor 里。

    关闭流程(:meth:`close`)仅委托给 :attr:`barrier`(ADR-0169 D5):
        cursor.close(reason) → writable.iteration.closing EP
        → barrier.close(reason) → Persistence.flush → Host.flush_all → close EP emit
    """

    cursor_factory: LoopCursorFactory
    projection_host: StdProjectionHost
    persistence: Any  # PersistenceCoordinator(protocol 位;由调用方注入)
    capture: ModelVisibleCapture
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
        run_dir: Path | str | None = None,
    ) -> ObservabilityRuntime:
        """Profile → 五缝 + CloseBarrier 装配(ADR-0169 §D8 / PR-25)。

        Parameters
        ----------
        profile:
            Profile / ResolvedProfile / 任意 duck-typed 对象;读 ``plan_ref`` /
            ``observability`` 段(可缺省)。
        ctx:
            cordis Context(留作未来 K5 接入点;PR-25 仅占位)。
        persistence:
            :class:`PersistenceCoordinator` 实例;**必传**(barrier 注入需要)。
            PR-25 阶段 runtime 不自己构造 persistence —— 那是 PR-15 的职责。
        run_dir:
            run 输出目录;用于 ModelVisibleCapture。缺省 ``traces/runs/<run_id>``。

        Returns
        -------
        ObservabilityRuntime
            已 frozen 的五缝容器;调用方存到 ctx / ProfileBootProducts。
        """
        plan_ref = str(getattr(profile, "plan_ref", "default"))

        # 1) cursor factory —— 单一实例,每次 make_cursor 派生新 cursor
        cursor_factory = LoopCursorFactory()

        # 2) projection host —— 默认注册清单(profile.observability.projection_host.initial)
        initial = _extract_projection_initial(profile)
        projection_host = StdProjectionHost(initial=initial or None)

        # 3) model visible capture —— run_dir 来自 profile.runs_root 或入参
        resolved_run_dir = (
            Path(run_dir) if run_dir is not None else Path(_extract_runs_root(profile))
        )
        capture: ModelVisibleCapture = StdModelVisibleCapture(run_dir=resolved_run_dir)

        # 4) close barrier —— 由 runtime 持有;cursor 关闭时委托给它
        #    barrier 需要 persistence / host / emitter;emitter = cursor 自身
        barrier: CloseBarrier = StdCloseBarrier(
            persistence=persistence,  # type: ignore[arg-type]
            host=projection_host,
            close_emitter=_NullCloseEmitter(),  # cursor 自身是 emitter,barrier 仅协调顺序
        )

        return cls(
            cursor_factory=cursor_factory,
            projection_host=projection_host,
            persistence=persistence,
            capture=capture,
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
        cursor, _incarnation = self.cursor_factory.from_profile(
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


def _extract_runs_root(profile: Any) -> str:
    """从 profile 读 ``runs_root`` 路径;缺省 ``traces/runs/<unknown>``。"""
    if hasattr(profile, "runs_root"):
        return str(profile.runs_root)
    return "traces/runs/unknown"


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
