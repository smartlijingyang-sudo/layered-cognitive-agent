"""Assemble a Run, drive Agent/Team, tear down exactly once."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Sequence
from contextlib import nullcontext
from typing import Any, cast

import structlog

from gateway.modes import DEFAULT_MODE
from gateway.runs import terminalizer
from gateway.runs._journal_factory import (
    create_run_journal_components as _create_run_journal_components,
)
from gateway.runs.identity import AgentRef, default_agent_ref
from gateway.runs.intent import resolve_run_intent
from gateway.runs.live import LiveTail
from gateway.runs.session import RunRegistry, RunSession, RunStatus
from gateway.runs.terminalizer import RunTerminalizer
from lca.contracts.atoms.ids import RunId, TraceId, new_id
from lca.contracts.mechanisms.capability import (
    MissingCapabilityError,
    provider_current,
    require_capability,
)
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY, ConversationTurn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.plane import PlaneBindings, PlaneKind
from lca.contracts.models.observability.diagnostic import DiagnosticCategory
from lca.contracts.models.observability.journal import (
    AttachmentStagingCompleted,
    AttachmentStagingFailed,
    AttachmentStagingStarted,
    RunScope,
)
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols import JournalProjector
from lca.contracts.protocols.infra import Sandbox
from lca.layer0_infra.attachment import FileStoreAttachmentIdentity
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.observability import (
    BoundObservability,
    bind_backends,
    record,
    record_runtime,
    run_scope,
)
from lca.layer0_infra.observability.event_descriptor_env import bind_descriptors
from lca.layer0_infra.observability.settings import ObservabilitySettings
from lca.layer0_infra.plane.machine import resolve_machine, resolve_machine_transport
from lca.layer0_infra.plane.resolve import (
    PlaneBindingError,
    PlaneRequest,
    ref_of,
    resolve_plane_bindings,
    sandbox_ref_from,
)
from lca.layer0_infra.plane.scope import plane_bindings_scope
from lca.layer0_infra.sandbox.runtime_scope import bind_sandbox_runtime
from lca.layer0_infra.search.scope import search_run_scope
from lca.layer0_infra.tools.run_attachment_scope import run_attachment_scope
from lca.layer0_infra.tools.run_finalizer import run_id_scope
from lca.layer0_infra.workspace import run_workspace_scope
from lca.plugins.loop_drivers.registry import (
    _UnknownExecutionTargetError as _UnknownExecutionTargetError,
)

_log = structlog.get_logger(__name__)

_EXPORT_DISPOSE_TIMEOUT_S = 3.0

_SANITIZE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"DataInspectionFailed|content.?filter|inappropriate.?content|content.?safety",
            re.IGNORECASE,
        ),
        "模型输出触发了内容安全策略，请调整输入后重试",
    ),
    (
        re.compile(r"<\d{3}>|APIError|APIConnectionError|APITimeoutError|InternalError"),
        "模型服务暂时不可用，请稍后重试",
    ),
    (
        re.compile(r"timeout|connection|network", re.IGNORECASE),
        "网络连接异常，请检查网络后重试",
    ),
)


def llm_status(ctx: Any) -> dict[str, bool]:
    """Whether the boot tree's resolver can hand out a real adapter.

    Gateway endpoints may be reached before the application lifespan creates
    the plugin context. That is an expected availability state, not an
    attribute error that should escape as HTTP 500.
    """
    if ctx is None:
        return {"llm_available": False}
    try:
        resolver = ctx.inject("llm_resolver")
    except (AttributeError, KeyError):
        return {"llm_available": False}
    return {"llm_available": resolver.is_available()}


def sanitize_error(error: str) -> str:
    """Three regexes. No sanitizer protocol theatre."""
    if not error:
        return error
    for pattern, replacement in _SANITIZE_RULES:
        if pattern.search(error):
            return replacement
    return error


def format_user_error(error: str, *, run_id: str, trace_id: str) -> str:
    """结构化错误消息：用户可读原因 + debug 上下文。

    内部异常类名前缀（``_UnknownExecutionTargetError:`` / ``KeyError:`` 等）
    在拼装之前剥掉——终端用户不应看到 Python 内部符号。
    """
    user_facing = _strip_internal_exception_prefix(sanitize_error(error))
    return f"{user_facing}\nrun: {run_id} | trace: {trace_id}"


_INTERNAL_EXCEPTION_PREFIX = re.compile(r"^_*[A-Z][A-Za-z0-9._]*Error:\s*")


def _strip_internal_exception_prefix(error: str) -> str:
    """去掉形如 ``KeyError: foo`` / ``_UnknownExecutionTargetError: bar`` 的前缀。"""
    return _INTERNAL_EXCEPTION_PREFIX.sub("", error or "", count=1)


def assemble_run_hub(
    *,
    jsonl_writer: JournalProjector,
    tail: LiveTail,
    ctx: Any,
    settings: ObservabilitySettings | None = None,
    extra_projectors: Sequence[JournalProjector] = (),
) -> BoundObservability:
    """Run-scoped BoundObservability：基线 (boot readers) + run writers。

    boot 期 ``assemble_observability`` 已构造 ``BoundObservability`` 并通过
    ``ctx.provide("observability", bound)`` 挂上；本函数从基线 Bound 出发，
    把 jsonl 落盘、LiveTail SSE、跨 run ProcessJournal 等 run-scoped writer
    追加到 journal 上，返回新 BoundObservability（immutable，原基线不动）。

    ADR-0065 L9 / PR-5: ``JsonlJournalProjector`` / ``LiveTail`` 实例化集中
    在 ``gateway/runs/_journal_factory.py``。调用方经 ``create_run_journal_components``
    拿到 ``(jsonl_writer, tail)`` 后传入本函数。

    Diagnostics go through the journal (see ``diagnostics_enabled``); no
    separate diagnostic sink needed.
    """
    from lca.harness.observability import make_minimal_bound

    # settings 形参保留以兼容外部调用方；新模型 settings 由 boot 期
    # assemble_observability 一次性消费，run 边不再二次解析。
    try:
        base: BoundObservability = require_capability(ctx, "observability")
    except MissingCapabilityError:
        # boot 未挂 observability（极端测试场景）：退回最小可用 bound，
        # 业务事件仍可写到 local store。
        from lca.layer0_infra.observability.facade import BoundObservability
        from lca.layer0_infra.observability.policy import AttributePolicy

        minimal = make_minimal_bound()
        return BoundObservability(
            journal=minimal.journal,
            tracer=minimal.tracer,
            policy=AttributePolicy(),
            scorers=minimal.scorers,
        )
    run_bound = base.with_journal_projection(jsonl_writer)
    run_bound = run_bound.with_journal_projection(tail)
    for projection in extra_projectors:
        run_bound = run_bound.with_journal_projection(projection)
    return run_bound


def create_hub_for_session(
    session: RunSession,
    *,
    ctx: Any,
    settings: ObservabilitySettings | None = None,
) -> BoundObservability:
    """Used by tests that assemble a session first. Production uses create_run_session."""
    if session.hub is not None:
        return session.hub
    # ADR-0065 PR-5: writer 由 factory 装配,不再直接 new。
    jsonl_writer, _tail = _create_run_journal_components(
        jsonl_path=session.jsonl_path,
    )
    hub = assemble_run_hub(
        jsonl_writer=jsonl_writer,
        tail=session.tail,
        ctx=ctx,
        settings=settings,
    )
    session.hub = hub
    return hub


def create_run_session(
    registry: RunRegistry,
    *,
    question: str,
    user_text: str,
    mode: str = DEFAULT_MODE,
    attachment_ids: Sequence[str] = (),
    prior_turns: Sequence[ConversationTurn] = (),
    agent: AgentRef | None = None,
    device_id: str = "",
    plane: str = "",
    extra_plane: str = "",
    execution_target: str = "",
    ctx: Any,
) -> RunSession:
    run_id = new_id("run")
    trace_id = new_id("trace")
    jsonl_path = registry.jsonl_path_for(run_id)
    cleaned_ids = tuple(str(i).strip() for i in attachment_ids if str(i).strip())
    # ADR-0065 PR-5: writer 由 factory 装配,tail 由 factory 装配。
    jsonl_writer, tail = _create_run_journal_components(
        jsonl_path=jsonl_path,
    )
    hub = assemble_run_hub(
        jsonl_writer=jsonl_writer,
        tail=tail,
        ctx=ctx,
        extra_projectors=(registry.journal.bind(),),
    )
    session = RunSession(
        run_id=run_id,
        trace_id=trace_id,
        jsonl_path=jsonl_path,
        tail=tail,
        hub=hub,
        question=question,
        user_text=user_text,
        mode=mode,
        prior_turns=tuple(prior_turns),
        attachment_ids=cleaned_ids,
        agent=agent if agent is not None else default_agent_ref(),
        device_id=device_id.strip(),
        plane=plane.strip(),
        extra_plane=extra_plane.strip(),
        execution_target=execution_target.strip(),
        started_at=time.time(),
        locator=registry.locator(),
    )
    registry.put(session)
    _emit_plugin_inventory(session, ctx, hub)
    return session


def _emit_plugin_inventory(session: RunSession, ctx: Any, hub: BoundObservability) -> None:
    """记录本 run 使用的插件声明摘要，不暴露配置值或密钥。"""
    entries = tuple(getattr(ctx, "entries", ()) or ())
    plugins = [
        "|".join(
            (
                str(getattr(entry, "id", "")),
                f"requires={','.join(getattr(entry, 'inject', ()) or ())}",
                f"provides={','.join(getattr(entry, 'provides', ()) or ())}",
            )
        )
        for entry in entries
    ]
    with (
        bind_backends(hub),
        run_scope(
            RunScope(
                trace_id=cast("TraceId", session.trace_id),
                run_id=cast("RunId", session.run_id),
            )
        ),
    ):
        record_runtime(
            DiagnosticCategory.PLUGIN,
            "plugin.inventory",
            plugin="profile.boot",
            attributes={"plugin_count": len(plugins)},
            output={"plugins": plugins},
        )


async def execute_run(
    registry: RunRegistry,
    *,
    run_id: str,
    question: str,
    mode: str = DEFAULT_MODE,
    ctx: Any,
) -> None:
    """Drive one Run. ``ctx`` is the boot-time plugin tree.

    The boot-time plugin tree is non-optional: callers must supply a
    booted ``ctx``. The legacy "pass None, fall back to a global cache"
    path is gone — boot once during server startup, then hand the same
    ``ctx`` to every run.
    """
    session = registry.get(run_id)
    if session is None:
        return
    session.status = RunStatus.RUNNING
    hub = session.hub if session.hub is not None else create_hub_for_session(session, ctx=ctx)
    workspace_ref: list[Any] = [None]
    success = False
    try:
        with (
            run_id_scope(session.run_id),
            run_attachment_scope(session.attachment_ids),
            run_workspace_scope(session.run_id) as workspace,
            search_run_scope(),
            run_scope(
                RunScope(
                    trace_id=cast("TraceId", session.trace_id),
                    run_id=cast("RunId", session.run_id),
                )
            ),
        ):
            structlog.contextvars.bind_contextvars(
                run_id=session.run_id,
                trace_id=session.trace_id,
            )
            workspace_ref[0] = workspace
            try:
                bindings = _freeze_bindings(session, ctx)
            except PlaneBindingError as exc:
                session.error = str(exc)
                _record_run_failure(session, exc, hub)
                return
            except _UnknownExecutionTargetError as exc:
                session.error = str(exc)
                _record_run_failure(session, exc, hub)
                return
            session.bindings = bindings
            driver_registry = require_capability(ctx, "run_loop_driver_registry")
            intent = resolve_run_intent(
                driver_registry,
                execution_target=session.execution_target,
                plane=session.plane,
                extra_plane=session.extra_plane,
                device_id=session.device_id,
            )
            driver = intent.driver
            sandbox_svc = require_capability(ctx, "sandbox")
            sandbox = provider_current(sandbox_svc)
            if sandbox is None or ref_of(bindings, PlaneKind.SANDBOX) is None:
                sandbox = None
            file_store = provider_current(require_capability(ctx, "file_store"))
            with plane_bindings_scope(bindings):
                if sandbox is not None and file_store is not None:
                    try:
                        await bind_sandbox_runtime(
                            session.run_id,
                            cast("Sandbox", sandbox),
                            cast("FileStore", file_store),
                            session.attachment_ids,
                        )
                    except Exception as exc:
                        _log.warning(
                            "sandbox_runtime_bind_failed",
                            hop="H2",
                            run_id=session.run_id,
                            error=str(exc),
                        )
                # ADR-0065 L4: run 边把 boot 期注入的 EventDescriptorRegistry 装到
                # ambient ContextVar,供 SSE 帧选择器 / 控制台渲染器 / Inspector
                # 走 cordis 路径(RunStore 走 self._descriptor_registry 直传,无需
                # ContextVar)。无 boot registry 时(specialty 测试)退回 module fallback。
                _descriptor_registry = ctx.inject("event_descriptor_registry", default=None)
                if _descriptor_registry is None:
                    from lca.layer0_infra.observability.event_catalog import (
                        EVENT_DESCRIPTOR_REGISTRY,
                    )

                    _descriptor_registry = EVENT_DESCRIPTOR_REGISTRY

                with bind_backends(hub), bind_descriptors(_descriptor_registry):
                    await _stage_machine_attachments(session, file_store)
                    outcome = await driver.execute(
                        session,
                        question=question,
                        mode=mode,
                        hub=hub,
                        bindings=bindings,
                        run_context=_run_context_for_session(session),
                        ctx=ctx,
                    )
                    if outcome.waiting_input:
                        session.status = RunStatus.WAITING_INPUT
                        session.declarative_checkpoint = outcome.declarative_checkpoint
                        session.runnable = outcome.resumable
                        session.approval_request = outcome.approval_request
                        _log.info(
                            "run_paused_for_input",
                            hop="H2",
                            run_id=session.run_id,
                            approval_type=session.approval_request.get("type")
                            if session.approval_request
                            else None,
                        )
                        return
                    success = outcome.success
                    if not success and not session.error and outcome.error:
                        session.error = format_user_error(
                            outcome.error,
                            run_id=session.run_id,
                            trace_id=session.trace_id,
                        )
    except asyncio.CancelledError:
        session.cancel_requested = True
        raise
    except Exception as exc:
        _log.exception(
            "run_failed",
            run_id=session.run_id,
            trace_id=session.trace_id,
            error_type=type(exc).__name__,
        )
        session.error = format_user_error(
            f"{type(exc).__name__}: {exc}",
            run_id=session.run_id,
            trace_id=session.trace_id,
        )
        _record_run_failure(session, exc, hub)
    finally:
        structlog.contextvars.clear_contextvars()
        if session.status == RunStatus.WAITING_INPUT:
            registry.mark_paused(session)
        else:
            await RunTerminalizer(registry).terminalize(
                session, workspace=workspace_ref[0], success=success
            )


async def resume_run(session: RunSession, registry: RunRegistry, answer: str) -> None:
    """HIL resume. Same finalize as execute. Must not close tail while waiting."""
    success = False
    session.status = RunStatus.RUNNING
    try:
        bindings = session.bindings
        scope = plane_bindings_scope(bindings) if bindings is not None else nullcontext()
        with scope:
            result = await session.runnable.resume(
                session.declarative_checkpoint,
                input=answer,
            )
        if result.status == TaskStatus.INPUT_REQUIRED and result.extra.get("outcome") == "paused":
            session.status = RunStatus.WAITING_INPUT
            session.declarative_checkpoint = result.extra.get("declarative_checkpoint")
            session.approval_request = result.extra.get("approval_request")
            registry.mark_paused(session)
            return
        success = result.status == TaskStatus.COMPLETED
        if not success and not session.error and result.error:
            session.error = format_user_error(
                result.error,
                run_id=session.run_id,
                trace_id=session.trace_id,
            )
    except asyncio.CancelledError:
        session.cancel_requested = True
        raise
    except Exception as exc:
        _log.exception(
            "run_resume_failed",
            run_id=session.run_id,
            trace_id=session.trace_id,
            error_type=type(exc).__name__,
        )
        session.error = format_user_error(
            f"{type(exc).__name__}: {exc}",
            run_id=session.run_id,
            trace_id=session.trace_id,
        )
        _record_run_failure(session, exc, session.hub)
    finally:
        if session.status == RunStatus.WAITING_INPUT:
            registry.mark_paused(session)
        else:
            await RunTerminalizer(registry).terminalize(session, workspace=None, success=success)


def _record_run_failure(session: RunSession, exc: BaseException | None, hub: Any) -> None:
    """Record an observable failed run before terminalization closes the journal."""

    if hub is None:
        return
    from lca.contracts.models.core.lifecycle import TaskStatus
    from lca.contracts.models.observability.journal import AgentRunFinished, AgentRunStarted

    message = session.error or (f"{type(exc).__name__}: {exc}" if exc else "run failed")
    try:
        with (
            bind_backends(hub),
            run_scope(
                RunScope(
                    trace_id=cast("TraceId", session.trace_id),
                    run_id=cast("RunId", session.run_id),
                )
            ),
        ):
            record(
                AgentRunStarted(
                    agent_role=session.agent.name if session.agent else "",
                    strategy_key=session.mode,
                    objective=session.user_text,
                    objective_preview=session.user_text[:200],
                    from_role="",
                )
            )
            record(
                AgentRunFinished(
                    status=TaskStatus.FAILED.value,
                    output_text="",
                    steps=0,
                    error=message,
                )
            )
    except Exception:
        _log.warning("run_failure_journal_failed", run_id=session.run_id, exc_info=True)


def _record_terminal_materialization(session: RunSession) -> None:
    """Compatibility wrapper for terminal-manifest callers."""

    terminalizer._record_terminal_materialization(session)


async def finalize(
    session: RunSession,
    registry: RunRegistry,
    workspace: Any,
    success: bool,
) -> None:
    """Compatibility entry point for callers that finalize a run directly."""

    await RunTerminalizer(registry).terminalize(session, workspace=workspace, success=success)


def _freeze_bindings(session: RunSession, ctx: Any) -> PlaneBindings:
    sandbox = cast("Sandbox | None", provider_current(require_capability(ctx, "sandbox")))
    sandbox_ref = sandbox_ref_from(sandbox) if sandbox is not None else None
    machine = resolve_machine(session.device_id or None)
    bindings = resolve_plane_bindings(
        machine,
        sandbox_ref,
        PlaneRequest(
            device_id=session.device_id,
            plane=session.plane,
            extra_plane=session.extra_plane,
            execution_target=session.execution_target,
        ),
    )
    machine_bound = ref_of(bindings, PlaneKind.MACHINE)
    if machine_bound is not None:
        _log.info(
            "plane_bound",
            kind=machine_bound.kind.value,
            plane_id=machine_bound.id,
            root=machine_bound.root,
            role="machine",
        )
    if bindings.primary is not None:
        _log.info(
            "plane_primary",
            kind=bindings.primary.kind.value,
            plane_id=bindings.primary.id,
            root=bindings.primary.root,
        )
    return bindings


async def _stage_machine_attachments(session: RunSession, store: Any | None) -> None:
    """附件暂存——系统 bootstrap 通道，等价于 Sandbox.write_files()。"""
    if session.bindings is None:
        return
    machine = ref_of(session.bindings, PlaneKind.MACHINE)
    if machine is None or not session.attachment_ids:
        return
    if store is None:
        raise MissingCapabilityError("file_store")
    transport = resolve_machine_transport(machine.id)
    if transport is None:
        raise RuntimeError(f"machine {machine.label} offline; cannot stage attachments")
    files = FileStoreAttachmentIdentity(store).stage_payload(session.run_id, session.attachment_ids)
    if not files:
        raise RuntimeError(
            f"machine attachments missing in FileStore: {list(session.attachment_ids)}"
        )
    total_bytes = sum(len(v) for v in files.values())
    record(
        AttachmentStagingStarted(
            plane_id=machine.id,
            file_count=len(files),
            total_bytes=total_bytes,
            run_id=session.run_id,
        )
    )
    started = time.monotonic()
    try:
        # write_files signature expects ``dict[str, bytes | str]``; we have
        # ``dict[str, bytes]``. Mapping is covariant in the value, so cast
        # through a read-only view to satisfy invariance.
        result = await transport.write_files(
            cast("dict[str, bytes | str]", files),
            base_dir=machine.root,
        )
    except Exception as exc:
        _log.exception(
            "attachment_staging_transport_error",
            run_id=session.run_id,
            plane_id=machine.id,
        )
        record(
            AttachmentStagingFailed(
                plane_id=machine.id,
                error=f"{type(exc).__name__}: {exc}",
                failed_paths=tuple(files.keys()),
                run_id=session.run_id,
            )
        )
        raise
    duration_ms = (time.monotonic() - started) * 1000
    if getattr(result, "success", True) is False:
        error_msg = str(getattr(result, "error", result))
        record(
            AttachmentStagingFailed(
                plane_id=machine.id,
                error=error_msg,
                failed_paths=tuple(files.keys()),
                run_id=session.run_id,
            )
        )
        raise RuntimeError(f"附件暂存失败（{len(files)} 个文件）: {error_msg}")
    record(
        AttachmentStagingCompleted(
            plane_id=machine.id,
            file_count=len(files),
            total_bytes=total_bytes,
            duration_ms=duration_ms,
        )
    )


def _run_context_for_session(session: RunSession) -> RunContext:
    extra: dict[str, Any] = {
        "agent_id": session.agent.agent_id,
        "agent_name": session.agent.name,
    }
    if session.prior_turns:
        extra[PRIOR_CONVERSATION_WM_KEY] = [
            {"role": t.role, "content": t.content} for t in session.prior_turns
        ]
    return RunContext(session_id=session.agent.agent_id, extra=extra)


def schedule_run(
    registry: RunRegistry,
    session: RunSession,
    *,
    ctx: Any,
) -> asyncio.Task[Any]:
    task = asyncio.create_task(
        execute_run(
            registry,
            run_id=session.run_id,
            question=session.question,
            mode=session.mode,
            ctx=ctx,
        )
    )
    session.task = task
    return task
