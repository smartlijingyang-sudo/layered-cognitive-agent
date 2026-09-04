"""Build one coherent legacy RunSession from request and runtime bindings.

ADR-0068 §决策二 + ADR-0167 D11 + ADR-0186 PR-3g:
    - 构造 ``StepCoordinator``。
    - step_tree 由 transport 在 ``RunSessionBuilder.build`` 装配
      ``StepTreeFoldDeriver``;flush 时从 Session 快照或 SpineReader fold。
    - journal.json 落盘由 StepTreeFoldDeriver.flush() 触发。
    - narrative.md 落盘由 NarrativeDeriver.write() 触发。
    - phase_graph.dot 落盘由 GraphDeriver.flush() 触发。
    - ``session.plan_ref`` 是 CompiledRunPlan 的 16-hex 稳定 ID(declarative
      路径)或 mode/profile/agent 的稳定 fingerprint(solo 路径),由
      :func:`_compute_plan_ref` 在 build 阶段一锤定音,后续 reader(manifest、
      profile_snapshot、deriver、_ProfileProxy)都读同一个值,避免字段重复
      声明成"三个不同含义"的 plan_ref。
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from lca.contracts.atoms.ids import new_id
from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.observability.run_journal import RunJournalFactory
from lca.harness.plan import compiled_run_plan_ref
from lca.harness.profile.boot_products import compiled_plan_from_scope
from lca.infrastructure.observability.loop_cursor.bind import (
    SpineWritePortAdapter,
    install_run_cursor,
)
from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
    NullPersistenceCoordinator,
)
from lca.infrastructure.observability.writable_matrix.registry import (
    WritableFaceRegistry,
)
from lca.plugins.session.derivers.step_tree import StepTreeFoldDeriver
from lca.plugins.transport.webserver.handlers.runs.observability.binding import assemble_run_hub
from lca.plugins.transport.webserver.handlers.runs.observability.identity import default_agent_ref
from lca.plugins.transport.webserver.handlers.runs.session.event_session import (
    bind_run_event_session,
    unbind_run_event_session,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry, RunSession
from lca.plugins.transport.webserver.handlers.runs.session.setup_types import RunSessionRequest
from lca.runtime.journal_setup import BuildJournalMetadata, build_step_coordinator
from lca_kernel.observability import ObservabilityRuntime

log = logging.getLogger(__name__)


def _compute_plan_ref(ctx: Any, request: RunSessionRequest) -> str:
    """SSOT for transport-layer plan_ref resolution.

    Resolution order (声明 ADR-0068 §决策二 的 "一条 plan_ref"):
        1. Declarative 路径(有 ``compiled_run_plan`` 在 ctx 上):
           直接用 ``compiled_run_plan_ref(plan)`` —— 16-hex 稳定 ID,
           与 ``DeclarativeRuntimeBindings.plan_ref()`` 同一来源。
        2. Solo / lobehub 路径(没有 declarative plan):
           fallback = ``sha256(profile_path|mode|agent_role|strategy)[:16]``
           —— 短但稳定,标识"哪个 profile / 哪种 agent / 哪种模式",
           未来需要严格 plan 复现时再走第 3 步(declarative path)。
        3. 都没有:返回空串 —— 与历史 ``session.plan_ref = ""`` 兼容,
           reader 看到空应理解为"未走 declarative plan 的 solo run"。

    旧实现里 ``request.mode`` 直接当 plan_ref("solo" 字面量),把"transport
    intent" 与 "runtime plan identity" 混为一谈,语义上撒谎。 本函数把两者
    显式分开:intent 仍走 ``request.mode`` 决定 driver;plan_ref 只走真值。
    """
    try:
        plan = compiled_plan_from_scope(ctx)
    except MissingCapabilityError:
        plan = None
    if plan is not None:
        return compiled_run_plan_ref(plan)
    # Solo fallback:fingerprint = profile_path + mode + role
    # 字段缺失时全部空串 join,保持稳定。
    parts = (
        getattr(request, "profile_path", "") or "default",
        request.mode or "solo",
        request.agent.name if request.agent is not None else "",
        request.execution_target or "",
    )
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class RunSessionBuilder:
    """Own identity allocation, carrier normalization, and run-local assembly."""

    def __init__(self, registry: RunRegistry, *, ctx: Any) -> None:
        self._registry = registry
        self._ctx = ctx

    def build(self, request: RunSessionRequest) -> RunSession:
        """Build a journal-enabled session without publishing it to the registry.

        ADR-0167 D11 / ADR-0186 PR-3g: 在 builder 阶段构造 ``StepCoordinator``
        + 装配 per-run ``StepTreeFoldDeriver``。flush 时从 Session 快照或
        SpineReader fold → journal.json / narrative.md。
        """
        run_id = new_id("run")
        trace_id = new_id("trace")
        started_at = time.time()
        agent = request.agent if request.agent is not None else default_agent_ref()
        cleaned_attachment_ids = _clean_attachment_ids(request.attachment_ids)

        # ADR-0068 §决策二:session.plan_ref 必须在 build 阶段就确定,
        # 是后续 manifest / profile_snapshot / deriver 的 SSOT。
        plan_ref = _compute_plan_ref(self._ctx, request)

        journal_factory = cast(
            "RunJournalFactory", require_capability(self._ctx, "run_ledger_factory")
        )

        # ── 1) 构造 StepCoordinator (WritableFaceRegistry 已 bind) ──
        try:
            registry = require_capability(self._ctx, "writable_face_registry")
        except MissingCapabilityError:
            # 缺 registry 时降级为 NullStorage 5 面 — 测试场景 / 单元测试用;
            # 生产 profile 必须显式装 writable.matrix.default。
            registry = WritableFaceRegistry()
            from lca.infrastructure.observability.writable_matrix import (
                LineCoalescer,
                NdjsonSerializer,
                NullStorage,
                SpineEmitter,
                StandardDriver,
            )

            registry.register("emitter", SpineEmitter())
            registry.register("driver", StandardDriver())
            registry.register("coalescer", LineCoalescer())
            registry.register("serializer", NdjsonSerializer())
            registry.register("storage", NullStorage())
        if not isinstance(registry, WritableFaceRegistry):
            raise RuntimeError(
                f"writable_face_registry must be WritableFaceRegistry,"
                f" got {type(registry).__name__}"
            )

        coordinator = build_step_coordinator(
            registry=registry,
            run_id=run_id,
            trace_id=trace_id,
            metadata=BuildJournalMetadata(
                agent_role=agent.name or agent.agent_id or "",
                strategy_key=request.mode or "solo",
                objective=request.user_text or "",
                started_at=started_at,
            ),
        )

        # ── 2) 取 spine / locator / deriver(必须在 1.5 cursor 之前) ──
        locator = self._registry.locator()
        run_dir = locator.run_dir(run_id) if locator is not None else None
        spine_path = self._registry.spine_path_for(run_id)

        spine_core = require_capability(self._ctx, "event_spine")
        # duck-type: SpineCore 有 .event_spine; tests / stub 提供裸 EventSpine
        event_spine = getattr(spine_core, "event_spine", None) or spine_core

        # ── 1.5) 装配 ObservabilityRuntime(ADR-0169 §D8 缝族) ────────────
        # 业务路径走 :meth:`ObservabilityRuntime.make_cursor` 派生 cursor
        # (不再手工 ``StdLoopCursor(...)``);persistence 缺省 fallback 到
        # NullPersistenceCoordinator(barrier 注入面不空)。
        # ADR-0185 PR-4:capture 缝已退场;model-visible 改由
        # ``ModelVisibleHook`` 在 LLM 边界走 spine event bus 拦截。
        spine_for_cursor = SpineWritePortAdapter(event_spine)
        # ``_ProfileProxy.plan_ref`` 之前误用 ``request.mode``(transport intent
        # 而非 plan identity),导致下游 ``loop_cursor`` 的 incarnation.plan_ref
        # 拿到 "solo" 而不是真 plan ID;这里统一读 SSOT(session.plan_ref)。
        profile_proxy = _ProfileProxy(plan_ref=plan_ref)
        runtime = ObservabilityRuntime.from_profile(
            profile=profile_proxy,
            ctx=self._ctx,
            persistence=NullPersistenceCoordinator(),  # 生产路径应注 File;此处 fallback
        )
        cursor = runtime.make_cursor(
            run_id=run_id,
            trace_id=trace_id,
            spine=spine_for_cursor,
        )
        cursor_token = install_run_cursor(cursor)

        # ADR-0186: bind Session before fold deriver so snapshot_events is available.
        event_session = bind_run_event_session(self._ctx, run_id)
        try:
            agent_role = agent.name or agent.agent_id or ""
            strategy_key = request.mode or "solo"
            objective = request.user_text or ""
            step_tree_deriver = _make_step_tree_deriver(
                ctx=self._ctx,
                run_id=run_id,
                run_dir=run_dir,
                spine_path=spine_path,
                agent_role=agent_role,
                strategy_key=strategy_key,
                plan_ref=plan_ref,
                objective=objective,
            )

            # ── 3) 注入 factory → 拿 LiveTail + 空 step_tree_writer ──
            components = journal_factory.create_run_components(
                spine_path=spine_path,
            )

            # ── 4) 把 step_tree_deriver + narrative_writer 装到 bundle ──
            bundle = components.step_tree_writer
            # bundle 是 frozen dataclass (_StepTreeBundle); 字段替换
            if bundle is not None and step_tree_deriver is not None:
                from dataclasses import replace as _dc_replace

                components = components.__class__(
                    writer=components.writer,
                    tail=components.tail,
                    step_tree_writer=_dc_replace(
                        bundle,
                        deriver=step_tree_deriver,
                    ),
                )

            # ── 5) assemble hub ──
            hub = assemble_run_hub(
                jsonl_writer=components.writer,
                tail=components.tail,
                ctx=self._ctx,
                extra_projectors=(self._registry.bind_process_journal(journal_factory),),
            )

            return RunSession(
                run_id=run_id,
                trace_id=trace_id,
                spine_path=spine_path,
                tail=components.tail,
                hub=hub,
                thread_tree_writer=step_tree_deriver,
                step_tree_bundle=components.step_tree_writer,
                coordinator=coordinator,
                loop_cursor=cursor,
                loop_cursor_token=cursor_token,
                question=request.question,
                user_text=request.user_text,
                mode=request.mode,
                plan_ref=plan_ref,
                prior_turns=tuple(request.prior_turns),
                attachment_ids=cleaned_attachment_ids,
                agent=agent,
                device_id=request.device_id.strip(),
                plane=request.plane.strip(),
                extra_plane=request.extra_plane.strip(),
                execution_target=request.execution_target.strip(),
                assistant_id=(getattr(request, "assistant_id", "") or "").strip(),
                started_at=started_at,
                locator=locator,
                event_session=event_session,
            )
        except BaseException:
            unbind_run_event_session(event_session)
            raise


def _lookup_event_session(ctx: Any, run_id: str) -> Any | None:
    """Return the in-process Session for ``run_id`` when ``session.store`` is wired."""
    try:
        store = require_capability(ctx, "session.store")
    except MissingCapabilityError:
        return None
    getter = getattr(store, "get", None)
    if not callable(getter):
        return None
    session = getter(run_id)
    if session is None or not callable(getattr(session, "snapshot_events", None)):
        return None
    return session


def _make_step_tree_deriver(
    *,
    ctx: Any,
    run_id: str,
    run_dir: Path | None,
    spine_path: Path,
    agent_role: str,
    strategy_key: str,
    plan_ref: str,
    objective: str,
) -> StepTreeFoldDeriver | None:
    """Assemble the production fold deriver. ``run_dir is None`` → skip journal.json."""
    if run_dir is None:
        return None
    deriver = StepTreeFoldDeriver(
        run_id=run_id,
        run_dir=run_dir,
        spine_path=spine_path,
        session=_lookup_event_session(ctx, run_id),
        agent_role=agent_role,
        strategy_key=strategy_key,
        plan_ref=plan_ref,
        objective=objective,
    )
    log.debug(
        "run_session_builder: fold step_tree deriver run=%s dir=%s",
        run_id,
        run_dir,
    )
    return deriver


def _clean_attachment_ids(values: Sequence[str]) -> tuple[str, ...]:
    """Normalize attachment carriers at the edge of session construction."""
    return tuple(str(item).strip() for item in values if str(item).strip())


class _ProfileProxy:
    """``ObservabilityRuntime.from_profile`` 接受的 duck-typed profile。

    ADR-0169 §D8 Runtime 是 profile duck-typed —— 只读 ``plan_ref``。
    web run 不持有完整 Profile 对象,只从
    :class:`RunSessionRequest` 派生必要字段。

    Attributes
    ----------
    plan_ref:
        profile 标识(用于 Incarnation.plan_ref);从 ``request.mode`` 派生。
    """

    __slots__ = ("plan_ref",)

    def __init__(self, *, plan_ref: str) -> None:
        self.plan_ref = plan_ref


__all__ = ["RunSessionBuilder"]
