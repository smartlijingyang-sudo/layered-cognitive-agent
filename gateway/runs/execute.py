"""Assemble a Run, drive Agent/Team, tear down exactly once."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Sequence
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import structlog

from gateway.modes import DEFAULT_MODE
from gateway.runs.doctor import diagnose
from gateway.runs.identity import AgentRef, default_agent_ref
from gateway.runs.live import LiveTail
from gateway.runs.loop_drivers import DEFAULT_RUN_DRIVERS
from gateway.runs.session import RunRegistry, RunSession, RunStatus
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY, ConversationTurn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.plane import PlaneKind
from lca.contracts.models.observability.journal import (
    AttachmentStagingCompleted,
    AttachmentStagingFailed,
    AttachmentStagingStarted,
    RunScope,
)
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.attachment import FileStoreAttachmentIdentity
from lca.layer0_infra.file_store import get_default_file_store
from lca.layer0_infra.llm_resolver import LLMResolver, ProductionLLMResolver
from lca.layer0_infra.observability import (
    ObservabilityHub,
    bind,
    create_observability,
    fold_run_state,
    record,
    run_scope,
)
from lca.layer0_infra.observability.journal.jsonl_projector import JsonlJournalProjector
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
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.sandbox.runtime_scope import bind_sandbox_runtime
from lca.layer0_infra.search.scope import search_run_scope
from lca.layer0_infra.tools.run_attachment_scope import run_attachment_scope
from lca.layer0_infra.tools.run_finalizer import finalize_run, run_id_scope
from lca.layer0_infra.workspace import run_workspace_scope

_log = structlog.get_logger(__name__)

_EXPORT_DISPOSE_TIMEOUT_S = 3.0

_default_llm_resolver: LLMResolver = ProductionLLMResolver()

_GATEWAY_SKIP_BACKENDS = frozenset({"console", "jsonl"})

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


def get_llm_resolver() -> LLMResolver:
    return _default_llm_resolver


def set_llm_resolver(resolver: LLMResolver) -> None:
    global _default_llm_resolver
    _default_llm_resolver = resolver


def llm_status() -> dict[str, bool]:
    return {"llm_available": get_llm_resolver().is_available()}


def _maybe_shadow_session(session: RunSession, question: str, result: Any) -> None:
    """When LCA_SESSION_SPINE=shadow, run the new path and log divergences."""
    from lca.harness.diagnostics.normalizer import compare_results
    from lca.harness.flags import session_spine_mode

    if session_spine_mode() != "shadow":
        return
    from gateway.spine import agent_registry, projections

    registry = agent_registry()
    proj = projections()
    if registry is None or proj is None:
        return

    import asyncio

    async def _run() -> None:
        handle = await registry.create(
            profile="web-standard",
            session_id=session.run_id,
        )
        from lca.contracts.harness.agent import UserMessage

        await handle.agent.followup(UserMessage(content=question))
        store = registry.store_for(session.run_id)
        snapshot = proj.snapshot(session.run_id)
        journal = list(store.events()) if store is not None else []
        report = compare_results(
            session_id=session.run_id,
            legacy=result,
            snapshot=snapshot,
            journal=journal,
        )
        if report.divergences:
            _log.warning("shadow_divergence", report=report.to_dict())
        else:
            _log.info("shadow_match", session_id=session.run_id)

    try:
        loop = asyncio.get_running_loop()
        session._shadow_task = loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())


def sanitize_error(error: str) -> str:
    """Three regexes. No sanitizer protocol theatre."""
    if not error:
        return error
    for pattern, replacement in _SANITIZE_RULES:
        if pattern.search(error):
            return replacement
    return error


def format_user_error(error: str, *, run_id: str, trace_id: str) -> str:
    """结构化错误消息：用户可读原因 + debug 上下文。"""
    sanitized = sanitize_error(error)
    if sanitized == error:
        return f"{sanitized}（run: {run_id}, trace: {trace_id}）"
    return f"{sanitized}\nrun: {run_id} | trace: {trace_id}"


def assemble_run_hub(
    *,
    jsonl_path: Path,
    tail: LiveTail,
    settings: ObservabilitySettings | None = None,
    extra_projectors: Sequence[JournalProjector] = (),
) -> ObservabilityHub:
    """Langfuse via create_observability; jsonl + tail + ops journal as readers."""
    cfg = settings if settings is not None else ObservabilitySettings()
    names = [name for name in cfg.backend_names() if name not in _GATEWAY_SKIP_BACKENDS]
    extra = [JsonlJournalProjector(jsonl_path), tail, *extra_projectors]
    return create_observability(
        "+".join(names),
        settings=cfg,
        extra_projectors=tuple(extra),
    )


def create_hub_for_session(
    session: RunSession,
    *,
    settings: ObservabilitySettings | None = None,
) -> ObservabilityHub:
    """Used by tests that assemble a session first. Production uses create_run_session."""
    if session.hub is not None:
        return session.hub
    hub = assemble_run_hub(jsonl_path=session.jsonl_path, tail=session.tail, settings=settings)
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
) -> RunSession:
    run_id = new_id("run")
    trace_id = new_id("trace")
    jsonl_path = registry.jsonl_path_for(run_id)
    cleaned_ids = tuple(str(i).strip() for i in attachment_ids if str(i).strip())
    tail = LiveTail()
    hub = assemble_run_hub(
        jsonl_path=jsonl_path,
        tail=tail,
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
    )
    registry.put(session)
    return session


async def execute_run(
    registry: RunRegistry,
    *,
    run_id: str,
    question: str,
    mode: str = DEFAULT_MODE,
) -> None:
    session = registry.get(run_id)
    if session is None:
        return
    session.status = RunStatus.RUNNING
    hub = session.hub if session.hub is not None else create_hub_for_session(session)
    workspace_ref: list[Any] = [None]
    success = False
    try:
        with (
            run_id_scope(session.run_id),
            run_attachment_scope(session.attachment_ids),
            run_workspace_scope(session.run_id) as workspace,
            search_run_scope(),
            run_scope(RunScope(trace_id=session.trace_id, run_id=session.run_id)),
        ):
            structlog.contextvars.bind_contextvars(
                run_id=session.run_id,
                trace_id=session.trace_id,
            )
            workspace_ref[0] = workspace
            try:
                bindings = _freeze_bindings(session)
            except PlaneBindingError as exc:
                session.error = str(exc)
                return
            session.bindings = bindings
            driver = DEFAULT_RUN_DRIVERS.resolve(session.execution_target)
            sandbox = (
                resolve_sandbox()
                if ref_of(bindings, PlaneKind.SANDBOX) and driver.uses_sandbox
                else None
            )
            with plane_bindings_scope(bindings):
                if sandbox is not None:
                    try:
                        await bind_sandbox_runtime(
                            session.run_id,
                            sandbox,
                            get_default_file_store(),
                            session.attachment_ids,
                        )
                    except Exception as exc:
                        _log.warning(
                            "sandbox_runtime_bind_failed",
                            hop="H2",
                            run_id=session.run_id,
                            error=str(exc),
                        )
                await _stage_machine_attachments(session)
                with bind(hub):
                    outcome = await driver.execute(
                        session,
                        question=question,
                        mode=mode,
                        hub=hub,
                        bindings=bindings,
                        run_context=_run_context_for_session(session),
                        llm_resolver=get_llm_resolver(),
                    )
                    if outcome.waiting_input:
                        session.status = RunStatus.WAITING_INPUT
                        session.snapshot = outcome.snapshot
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
                    if outcome.result is not None:
                        _maybe_shadow_session(session, question, outcome.result)
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
    finally:
        structlog.contextvars.clear_contextvars()
        if session.status == RunStatus.WAITING_INPUT:
            registry.mark_paused(session)
        else:
            await finalize(session, registry, workspace_ref[0], success)


async def resume_run(session: RunSession, registry: RunRegistry, answer: str) -> None:
    """HIL resume. Same finalize as execute. Must not close tail while waiting."""
    success = False
    try:
        bindings = session.bindings
        scope = plane_bindings_scope(bindings) if bindings is not None else nullcontext()
        with scope:
            result = await session.runnable.resume(session.snapshot, input=answer)
        if result.status == TaskStatus.INPUT_REQUIRED:
            session.status = RunStatus.WAITING_INPUT
            session.snapshot = result.extra.get("state_snapshot")
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
    await finalize(session, registry, None, success)


async def finalize(
    session: RunSession,
    registry: RunRegistry,
    workspace: Any,
    success: bool,
) -> None:
    """The only teardown. Nested finally. HIL must not call this.

    终态从 journal 推导（fold_run_state），不再独立写 status——消灭双 owner。
    cancel_requested 是 session 级信号，覆盖推导结果。
    """
    try:
        if session.hub is not None:
            _emit_artifact_closure_if_needed(workspace, session, session.hub)
        await finalize_run(session.run_id)
    except Exception:
        _log.exception("finalize_run_pre_close_failed", hop="H2", run_id=session.run_id)
    finally:
        try:
            if session.hub is not None:
                session.hub.release()
        finally:
            _derive_terminal_status(session, success)
            registry.clear_inflight(session.run_id)
            registry.prune()
            _record_doctor(session)
            if session.hub is not None:
                await _dispose_export(session.hub)


async def _dispose_export(hub: ObservabilityHub) -> None:
    """Langfuse / OTel teardown off the event loop. Live readers already closed."""
    try:
        await asyncio.wait_for(asyncio.to_thread(hub.dispose), timeout=_EXPORT_DISPOSE_TIMEOUT_S)
    except TimeoutError:
        _log.warning("observability_export_dispose_timeout", hop="H3")
    except Exception:
        _log.warning("observability_export_dispose_failed", hop="H3", exc_info=True)


def _derive_terminal_status(session: RunSession, success: bool) -> None:
    """终态推导：优先从 journal 事件流推导，fallback 到 session 信号。

    不变量 N3：状态是事件流的纯函数。cancel_requested 和 session.error
    是 session 级信号，在推导结果之上覆盖（处理 run 异常早退、无 finish 事件的场景）。
    """
    if session.cancel_requested:
        session.status = RunStatus.CANCELED
    elif session.error:
        session.status = RunStatus.FAILED
    elif session.hub is not None:
        derived = fold_run_state(session.hub.store.events)
        session.status = _journal_to_session_status(derived.status)
    else:
        _fallback_terminal_status(session, success)
    if session.status in {RunStatus.CANCELED, RunStatus.FAILED, RunStatus.COMPLETED}:
        session.closed_at = time.time()


def _journal_to_session_status(journal_status: object) -> RunStatus:
    """映射 journal reducer 的 RunStatus 到 session 的 RunStatus。"""
    from lca.layer0_infra.observability.journal.reducer import RunStatus as JRunStatus

    mapping = {
        JRunStatus.COMPLETED: RunStatus.COMPLETED,
        JRunStatus.FAILED: RunStatus.FAILED,
        JRunStatus.CANCELED: RunStatus.CANCELED,
        JRunStatus.RUNNING: RunStatus.COMPLETED,  # 无 finish 事件但 teardown 到达 → 视为完成
        JRunStatus.WAITING_INPUT: RunStatus.WAITING_INPUT,
    }
    return mapping.get(journal_status, RunStatus.COMPLETED)  # type: ignore[arg-type]


def _fallback_terminal_status(session: RunSession, success: bool) -> None:
    """Hub 不存在时的 fallback——保持旧行为。"""
    if session.error:
        session.status = RunStatus.FAILED
    elif success:
        session.status = RunStatus.COMPLETED


def _record_doctor(session: RunSession) -> None:
    try:
        report = diagnose(session, session.jsonl_path)
        if report.broken_hop or not report.factory["ok"]:
            _log.error(
                "run_doctor_verdict",
                hop=report.broken_hop or "factory",
                run_id=session.run_id,
                broken_hop=report.broken_hop,
                summary=report.summary,
            )
        doctor_path = session.jsonl_path.with_suffix(".doctor.json")
        doctor_path.write_text(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        _log.warning("run_doctor_failed", hop="H2", run_id=session.run_id, exc_info=True)


def _emit_artifact_closure_if_needed(
    workspace: Any, session: RunSession, hub: ObservabilityHub
) -> None:
    if workspace is None:
        return
    artifacts = workspace.artifacts.snapshot().artifacts
    if not artifacts:
        return
    closure = workspace.artifacts.closure_text()
    if not closure:
        return
    from lca.contracts.atoms.enums import StreamChannel
    from lca.contracts.models.observability.journal import StepTextDelta

    try:
        hub.store.append(
            StepTextDelta(
                step=-1,
                text_delta="\n\n" + closure,
                seq=0,
                channel=StreamChannel.ANSWER.value,
            )
        )
        _log.info(
            "artifact_closure_emitted",
            hop="H2",
            run_id=session.run_id,
            artifact_count=len(artifacts),
            status=session.status.value,
        )
    except Exception:
        _log.warning(
            "artifact_closure_emit_failed",
            hop="H2",
            run_id=session.run_id,
            exc_info=True,
        )


def _freeze_bindings(session: RunSession):
    sandbox = resolve_sandbox()
    sandbox_ref = sandbox_ref_from(sandbox) if sandbox is not None else None
    machine = resolve_machine(session.device_id or None)
    target = DEFAULT_RUN_DRIVERS.resolve(session.execution_target).plane_target
    if target is None:
        target = session.execution_target
    bindings = resolve_plane_bindings(
        machine,
        sandbox_ref,
        PlaneRequest(
            device_id=session.device_id,
            plane=session.plane,
            extra_plane=session.extra_plane,
            execution_target=target,
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


async def _stage_machine_attachments(session: RunSession) -> None:
    """附件暂存——系统 bootstrap 通道，等价于 Sandbox.write_files()。"""
    if session.bindings is None:
        return
    machine = ref_of(session.bindings, PlaneKind.MACHINE)
    if machine is None or not session.attachment_ids:
        return
    transport = resolve_machine_transport(machine.id)
    if transport is None:
        raise RuntimeError(f"machine {machine.label} offline; cannot stage attachments")
    store = get_default_file_store()
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
        result = await transport.write_files(files, base_dir=machine.root)
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
) -> asyncio.Task[Any]:
    task = asyncio.create_task(
        execute_run(
            registry,
            run_id=session.run_id,
            question=session.question,
            mode=session.mode,
        )
    )
    session.task = task
    return task
