"""K3:cordis Context + Fiber 启动(ADR-0115 K3 + ADR-0111 修订 + ADR-0116)。

K3 在启动全景中的位置
====================

K1–K2(纯函数,产出 ``ResolvedProfile`` + ``CompiledRunPlan``)
                      │
                      ▼
K3 run_kernel(本模块主入口)
                      │
                      ├─ 1) install_observability(基线,backend 全 no-op)
                      ├─ 2) for entry in BootEntry.from_resolved:
                      │       spawn_fiber + await_fiber
                      ├─ 3) attach_profile_boot_products(把 K2 产物挂到 ctx)
                      ├─ 4) install_observability(二次,registry 已填充,真 backend)
                      └─ 5) flush pending events:BootProfileResolved / BootObservabilityAssembled

K3 负责"声明层 → 运行层"的具体实例化。它**不重新做依赖解析**:
DAG 拓扑已在 K1b 阶段(`lca.harness.profile.resolve._topo_sort`)完成,
K3 只是按 ``ResolvedProfile.plugins`` 的顺序逐个 spawn fiber 并
``await setup(ctx, config)``。任何反向依赖会在 K1b 抛
``ProfileResolveError``,不会带着半残 ctx 进入 K3。

Public surface
--------------
- :func:`spawn_fiber` —— 注册一个 Fiber 到父 Context(供 plugin 装载)。
- :func:`run_kernel` —— 主入口:``ResolvedProfile`` → booted ``cordis.Context``。
- :func:`run_resolved_kernel` —— 已知 ``ResolvedProfile`` 的入口。
- :func:`stop_kernel` —— graceful shutdown(``ctx.dispose()``)。
- :func:`install_compile_result` —— 把编译产物 provide 到 ctx(transport 用)。
- :func:`boot_entries` —— 程序化 entries 的入口。

Boot 可观测性(ADR-0116 §决定 2)
-------------------------------
三个 typed JournalEvent 在 boot 路径上 emit:

- :class:`~lca.contracts.models.observability.journal.BootProfileResolved`
  boot 完成后:profile path / manifest hash / plugin count / bundle count /
  duration / 拓扑顺序。
- :class:`~lca.contracts.models.observability.journal.BootPluginFiberSpawned`
  每个 plugin fiber spawn 完成后一对 ``status=started/ok``。
- :class:`~lca.contracts.models.observability.journal.BootObservabilityAssembled`
  BoundObservability 装配完成后:bound seams / evidence store kind /
  journal_enabled / duration。

实现细节:由于 observability backend registries(``attribute_policy_backends``
/ ``journal_backends`` / ``tracer_backends`` / ``fact_scorers``)由 plugin 在
fiber spawn 时灌入 ctx,boot 顺序必须为 ``install_observability → spawn fibers
→ re-install observability → emit boot events``。第一遍 install 是基线
(no-op backends),第二遍 install 拿到已填充 registries 后真正写入 journal。
若 kernel 在测试 / 最小路径下没有 plugin,第二遍 install 仍安全 no-op。
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Any

from cordis import Context

from lca.contracts.models.observability.journal import (
    BootObservabilityAssembled,
    BootPluginFiberSpawned,
    BootProfileResolved,
)
from lca.harness.plugin_api import PluginDefinition

# boot_products is the seam's source-of-truth (compat-only in PR-2 sense);
# the kernel still imports the data classes from the legacy module path.
from lca.harness.profile.boot_products import (
    ProfileBootProducts,
    attach_profile_boot_products,
    compile_profile_boot_products,
    compiled_plan_from_scope,
    profile_boot_products_from_scope,
    resolved_profile_from_scope,
)
from lca.harness.profile.boot_projection import BootEntry
from lca.harness.profile.resolve import ResolvedProfile, resolve_entries
from lca.infrastructure.file_store import FileStore
from lca_kernel.errors import KernelError, StageError
from lca_kernel.observability import install_observability
from lca_kernel.stages import Stage


def spawn_fiber(ctx: Context, definition: PluginDefinition, config: Any) -> Any:
    """K3 工具:注册一个 Fiber 到父 Context(ADR-0062 §4 cordis Fiber Boot)。

    本函数**只 spawn 不 await**;用于 kernel 层单元测试和
    ``_boot_context`` 内部主循环(主循环里手工 ``await _await_fiber_for``)。
    生产 K3 路径的入口是 :func:`run_kernel`。

    K3 主循环细节见模块 docstring 的"K3 在启动全景中的位置"段。
    """
    from lca.harness.plugin_api import (
        AuditedPluginContext,  # ↑ K3:带 audit 包装的 PluginContext(记录 plugin 行为)
    )

    async def setup(_fiber_ctx: Context, fiber_config: Any) -> Any:  # ↑ K3:cordis 异步跑这个回调
        audited = AuditedPluginContext(
            ctx, definition
        )  # ↑ K3:用父 ctx 包装(共享 composition),不用 fiber_ctx
        return await _run_setup(
            definition.setup, audited, fiber_config
        )  # ↓ K3:跑 plugin 自己的 @plugin setup

    fiber = ctx.registry.plugin(  # ↓ K3:cordis registry 注册 fiber,返回 Fiber 对象
        {
            "name": definition.spec.id,  # ↑ K3:plugin id 作为 fiber 名
            "apply": setup,  # ↑ K3:cordis 异步跑上面那个 setup
            "inject": [],  # ↑ K3:不通过 cordis inject,setup 自己用 audited
            "Config": definition.Config,  # ↑ K3:Pydantic 配置模型(cordis 内部校验)
        },
        config=config,  # ↑ K3:已经过 Pydantic 校验的 config 实例
    )
    ctx.effect(
        fiber.dispose, label=f"plugin:{definition.spec.id}"
    )  # ↓ K6:把 fiber.dispose 登记成 effect,K6 退出时 LIFO 调
    return fiber  # ↑ K3:返回 fiber 句柄(主循环 await 它)


async def run_kernel(
    profile_path: Path | str,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """K3 主入口: 从 profile path 启动 cordis Context.

    Delegates to :func:`lca.harness.profile.boot.boot_profile`, which is
    the production boot implementation. The kernel is the single seam
    that compiles a profile into a running Context; it does NOT maintain
    a parallel boot implementation (the local ``_boot_context`` helper
    exists only to satisfy unit tests of :func:`_emit_boot_events`).

    完整 K 链路地图见模块 docstring 的"K3 在启动全景中的位置"段。
    """
    from lca.harness.profile.boot import (
        boot_profile,  # ↓ K3:跳到生产 boot 实现(同模块 _boot_context 主循环)
    )

    return await boot_profile(
        profile_path, bootstrap_file_store=bootstrap_file_store
    )  # ↑ K3:返回 booted cordis.Context


async def run_resolved_kernel(
    resolved: ResolvedProfile,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """K3 入口(已知 ``ResolvedProfile``):Boot an already-resolved profile.

    与 :func:`run_kernel` 的差别是省去 K1 阶段(直接拿 ``ResolvedProfile``);
    K2 计划编译会由 ``compile_profile_boot_products`` 内部完成。
    """
    from lca.harness.profile.boot import boot_resolved_profile

    return await boot_resolved_profile(resolved, bootstrap_file_store=bootstrap_file_store)


async def stop_kernel(ctx: Context) -> None:
    """K6 末步:Graceful shutdown — dispose the cordis Context.

    任何异常都被吞掉,因为调用方通常是 lifespan ``finally`` 子句,
    re-raise 会把原始退出信号淹没。
    """
    with contextlib.suppress(BaseException):
        await ctx.dispose()


def install_compile_result(ctx: Context, products: ProfileBootProducts) -> None:
    """K2 → transport 桥:把编译产物 provide 到 ctx。

    ADR-0115 决定 1:transport 只通过 ctx 拿 K2 编译产物,**不直接 import**
    ``ProfileBootProducts``。
    """
    if products is None:
        raise KernelError("install_compile_result requires a non-None ProfileBootProducts")
    attach_profile_boot_products(ctx, products)


async def boot_entries(
    entries: list[dict[str, Any]],
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """K3 程序化入口:Boot programmatic entries through the production Resolve semantics.

    与 :func:`run_kernel` 共享同一份 K1b/K2 校验链(``resolve_entries``),
    测试 fixture 不会演化出第二套解析语义。
    """
    resolved = resolve_entries(entries)  # ↓ K1b:程序化 entries 走 K1 域校验
    products = ProfileBootProducts(
        resolved_profile=resolved
    )  # ↑ K2:包成 boot products(K2 编译产物)
    return await _boot_context(
        products, bootstrap_file_store=bootstrap_file_store
    )  # ↓ K3:进入 K3 主循环,返回 booted ctx


# ── Internals ─────────────────────────────────────────────────────────


async def _boot_context(
    products: ProfileBootProducts,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """K3 内部:Boot one prepared plugin sequence with a single audited lifecycle seam.

    Boot ordering (ADR-0116 §决定 2 + ADR-0115 K5):

    1. ``install_observability(ctx)`` —— baseline,所有 backend None。
    2. 遍历 BootEntry,对每个 plugin ``spawn_fiber + await_fiber``,记录
       ``BootPluginFiberSpawned`` 到 ``pending_events``(journal 仍为 None,
       write() 安全 no-op)。
    3. ``install_observability(ctx)`` —— 第二次 install,registry 已被 plugin
       灌入,journal 真正可写。
    4. Flush pending events,emit ``BootProfileResolved`` + ``BootObservabilityAssembled``。

    完整 K 链路地图见模块 docstring 的"K3 在启动全景中的位置"段。
    """
    resolved = products.resolved_profile  # ↑ K1b:K1 产出的不可变声明
    if resolved is None:
        raise StageError(
            Stage.BOOT, "Profile boot requires a resolved profile"
        )  # ↑ K3:防御性,K1 失败时已抛错不会到这里
    ctx = Context()  # ↓ K3:进程级 cordis DI 容器(唯一,所有 plugin fiber 共享)
    boot_started = time.monotonic()  # ↑ K3:记 boot 起始时间,算 duration_ms
    plugin_started_at: dict[str, float] = {}  # ↑ K3:每个 plugin 的 spawn 起始时间
    pending_events: list[
        Any
    ] = []  # ↑ K3:暂存 BootPluginFiberSpawned 事件,等第 2 次 install_observability 后 flush
    try:
        # Step 1: baseline install (backends None).
        install_observability(ctx)  # ↓ K5:第 1 次,所有 backend None,plugin 还没灌入 registry
        # Step 2: spawn fibers, buffer BootPluginFiberSpawned.
        topo_order: list[str] = []  # ↑ K3:记录实际启动顺序(emit 给 BootProfileResolved)
        for entry in BootEntry.from_resolved(
            resolved
        ):  # ↓ K1b → K3:BootEntry 包装,顺序就是 K1b 拓扑序
            plugin_started_at[entry.definition.spec.id] = (
                time.monotonic()
            )  # ↑ K3:记这个 plugin 起始时间
            spec = entry.definition.spec
            pending_events.append(
                BootPluginFiberSpawned(  # ↑ K3:暂存 started 事件,journal 还没好先不写
                    plugin_id=spec.id,
                    layer=getattr(spec, "layer", "L0"),
                    kind=getattr(entry.definition, "kind", "provider"),
                    stage=Stage.BOOT,
                    duration_ms=0.0,
                    status="started",
                )
            )
            spawn_fiber(
                ctx, entry.definition, entry.config
            )  # ↓ K3:cordis registry 注册 fiber(返回不 await)
            await _await_fiber_for(
                ctx, entry.definition.spec.id
            )  # ↓ K3:等这个 fiber 真的跑完 setup(关键:顺序保证)
            if entry.definition.id == "lca-file-store-service" and bootstrap_file_store is not None:
                _bind_bootstrap_file_store(
                    ctx, bootstrap_file_store
                )  # ↑ K0:transport 注入自己的 FileStore 到 file_store seam
            finished_ms = (
                time.monotonic() - plugin_started_at[entry.definition.spec.id]
            ) * 1000  # ↑ K3:算这个 plugin 实跑毫秒
            # Replace the "started" placeholder with an "ok" outcome that carries the real duration.
            pending_events[-1] = (
                BootPluginFiberSpawned(  # ↑ K3:用 "ok" 事件替换占位 "started",带上真实 duration
                    plugin_id=spec.id,
                    layer=getattr(spec, "layer", "L0"),
                    kind=getattr(entry.definition, "kind", "provider"),
                    stage=Stage.BOOT,
                    duration_ms=finished_ms,
                    status="ok",
                )
            )
            topo_order.append(spec.id)  # ↑ K3:记入拓扑序
        attach_profile_boot_products(ctx, products)  # ↑ K2:K2 编译产物挂到 ctx,transport / 诊断可读
        # Step 2b: assemble the spine handler registry. Soft check only —
        # PR-3 sub-PRs are still landing reflectors, so a coverage gap is
        # expected and is logged as WARNING (not raised). The hard-fail
        # surface lives in tests/observability/spine/test_registry_completeness.
        _assemble_spine_registry(resolved)
        # Step 3: re-install observability with populated registries.
        install_observability(ctx)  # ↓ K5:第 2 次,plugin 已灌好 backend,BoundObservability 真正可写
        # Step 4: flush buffered events + emit final boot events.
        _emit_boot_events(  # ↓ K3:flush 3 个 boot 事件到 journal
            ctx,
            pending_events=pending_events,
            products=products,
            topo_order=tuple(topo_order),
            boot_started=boot_started,
        )
    except BaseException:  # ↑ K3:捕获所有异常(不只是 Exception),保证半残 ctx 也走 dispose
        await _dispose_context(ctx)  # ↑ K3:best-effort dispose,继续 raise 原始错误
        raise
    return ctx  # ↑ K3:返回 booted cordis.Context 给 K6


def _emit_boot_events(
    ctx: Context,
    *,
    pending_events: list[Any],
    products: ProfileBootProducts,
    topo_order: tuple[str, ...],
    boot_started: float,
) -> None:
    """Flush pending boot events and emit final BootProfileResolved / BootObservabilityAssembled.

    Journal may still be ``None`` (no plugin wired a journal backend) — in
    that case ``BoundObservability.journal.write`` is a documented safe
    no-op and we silently skip. The events are still recorded as boot
    diagnostic data via :class:`BootTrace` when observability re-installs
    with the journal available.
    """
    bound = _safe_inject(ctx, "observability")
    journal = getattr(bound, "journal", None) if bound is not None else None
    if journal is None:
        return
    obs_started = time.monotonic()
    for event in pending_events:
        with contextlib.suppress(Exception):
            journal.write(event)
    duration_ms = (time.monotonic() - boot_started) * 1000
    profile_path = str(
        getattr(products, "path", "") or getattr(products.resolved_profile, "path", "")
    )
    with contextlib.suppress(Exception):
        journal.write(
            BootProfileResolved(
                profile_path=profile_path,
                manifest_hash="",
                plugin_count=len(topo_order),
                bundle_count=0,
                duration_ms=duration_ms,
                topo_order=topo_order,
            )
        )
    bound_seams = tuple(
        name
        for name, present in (
            ("journal", getattr(bound, "journal", None) is not None),
            ("tracer", getattr(bound, "tracer", None) is not None),
            ("policy", getattr(bound, "policy", None) is not None),
            ("scorers", bool(getattr(bound, "scorers", ()))),
        )
        if present
    )
    with contextlib.suppress(Exception):
        journal.write(
            BootObservabilityAssembled(
                bound_seams=bound_seams,
                evidence_store_kind=type(getattr(bound, "evidence_store", None)).__name__
                if getattr(bound, "evidence_store", None) is not None
                else "none",
                journal_enabled=getattr(bound, "journal", None) is not None,
                duration_ms=(time.monotonic() - obs_started) * 1000,
            )
        )


def _safe_inject(ctx: Any, key: str) -> Any:
    """``ctx.inject(key, default=None)`` wrapper that handles both cordis Context and Protocol shapes."""
    inject = getattr(ctx, "inject", None)
    if not callable(inject):
        return None
    try:
        return inject(key, default=None)
    except (KeyError, TypeError):
        return None


def _bind_bootstrap_file_store(ctx: Context, store: FileStore) -> None:
    """Register the app-owned store before ordinary FileStore providers boot."""
    from lca.infrastructure.capability.files import FileStoreService

    service = ctx.inject("file_store")
    if not isinstance(service, FileStoreService):
        raise TypeError("file_store seam did not provide FileStoreService")
    service.register("app_bootstrap", store, activate=True)


async def _await_fiber_for(ctx: Context, plugin_id: str) -> None:
    """Wait for the named plugin's fiber to settle (best-effort)."""
    loader = ctx.inject("loader", default=None)
    if loader is None:
        return
    entries = list(loader.entries()) if hasattr(loader, "entries") else ()
    for entry in entries:
        if getattr(entry.options, "name", None) == plugin_id and entry.fiber is not None:
            await entry.fiber.await_()


async def _run_setup(setup_fn: Any, ctx: Any, config: Any) -> Any:
    """Invoke ``setup_fn(ctx, config)`` and await if it returned a coroutine."""
    result = setup_fn(ctx, config)
    if hasattr(result, "__await__"):
        return await result
    return result


async def _dispose_context(ctx: Context) -> None:
    """Best-effort dispose so the caller can re-raise the original boot error."""
    with contextlib.suppress(BaseException):
        await ctx.dispose()


def _assemble_spine_registry(resolved: ResolvedProfile) -> None:
    """Walk the resolved profile, assemble the spine handler registry,
    and log coverage gaps as a soft warning.

    Layer-1 / Layer-2 hard-fail enforcement lives in the pytest suite
    (``tests/observability/spine/test_registry_completeness``), not at
    runtime. The runtime kernel boot hook tolerates gaps so PR-3 sub-PRs
    (3.1–3.4) can land independently and the boot path remains
    unchanged when a future profile omits an EP that the close-set
    has not yet enforced.
    """
    from lca.harness.profile.compile_spine_registry import (  # ↓ K3:locally imported to avoid boot cycle
        compile_spine_registry,
        log_coverage_gaps,
    )

    registry = compile_spine_registry(resolved)
    log_coverage_gaps(registry)


__all__ = [
    "BootEntry",
    "ProfileBootProducts",
    "attach_profile_boot_products",
    "boot_entries",
    "compile_profile_boot_products",
    "compiled_plan_from_scope",
    "install_compile_result",
    "profile_boot_products_from_scope",
    "resolved_profile_from_scope",
    "run_kernel",
    "run_resolved_kernel",
    "spawn_fiber",
    "stop_kernel",
]
