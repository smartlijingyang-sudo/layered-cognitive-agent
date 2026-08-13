"""Assemble a Run, drive Agent/Team, tear down exactly once."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import structlog

from gateway.assemble import build_runnable_team, build_solo_agent
from gateway.modes import DEFAULT_MODE, SOLO_MODE_KEY
from gateway.runs.doctor import diagnose
from gateway.runs.identity import AgentRef, default_agent_ref
from gateway.runs.live import LiveTail
from gateway.runs.session import RunRegistry, RunSession, RunStatus
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY, ConversationTurn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.observability.journal import RunScope
from lca.contracts.models.team.run_context import RunContext
from lca.layer0_infra.file_store import get_default_file_store
from lca.layer0_infra.llm_resolver import LLMResolver, ProductionLLMResolver
from lca.layer0_infra.observability import ObservabilityHub, create_observability, run_scope
from lca.layer0_infra.observability.journal.jsonl_projector import JsonlJournalProjector
from lca.layer0_infra.observability.settings import ObservabilitySettings
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.sandbox.runtime_scope import bind_sandbox_runtime
from lca.layer0_infra.search.scope import search_run_scope
from lca.layer0_infra.tools.run_attachment_scope import run_attachment_scope
from lca.layer0_infra.tools.run_finalizer import finalize_run, run_id_scope
from lca.layer0_infra.workspace import run_workspace_scope
from lca.layer4_app.api import Agent, Team

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


def sanitize_error(error: str) -> str:
    """Three regexes. No sanitizer protocol theatre."""
    if not error:
        return error
    for pattern, replacement in _SANITIZE_RULES:
        if pattern.search(error):
            return replacement
    return error


def assemble_run_hub(
    *,
    jsonl_path: Path,
    tail: LiveTail,
    settings: ObservabilitySettings | None = None,
) -> ObservabilityHub:
    """Langfuse via create_observability; jsonl + tail as extra projectors."""
    cfg = settings if settings is not None else ObservabilitySettings()
    names = [name for name in cfg.backend_names() if name not in _GATEWAY_SKIP_BACKENDS]
    return create_observability(
        "+".join(names),
        settings=cfg,
        extra_projectors=(JsonlJournalProjector(jsonl_path), tail),
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
) -> RunSession:
    run_id = new_id("run")
    trace_id = new_id("trace")
    jsonl_path = registry.jsonl_path_for(run_id)
    cleaned_ids = tuple(str(i).strip() for i in attachment_ids if str(i).strip())
    tail = LiveTail()
    hub = assemble_run_hub(jsonl_path=jsonl_path, tail=tail)
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
            workspace_ref[0] = workspace
            sandbox = resolve_sandbox()
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
            llm = get_llm_resolver().resolve(mode=mode)
            runnable: Agent | Team
            if mode == SOLO_MODE_KEY:
                runnable = build_solo_agent(llm, observability=hub, role=session.agent.name)
            else:
                runnable = await build_runnable_team(
                    question,
                    llm,
                    observability=hub,
                    trace_id=session.trace_id,
                    run_id=session.run_id,
                )
            run_ctx = _run_context_for_session(session)
            if isinstance(runnable, Agent):
                result = await runnable.run(question, run_ctx)
            else:
                result = await runnable.run(question)
            if result.status == TaskStatus.INPUT_REQUIRED:
                session.status = RunStatus.WAITING_INPUT
                session.snapshot = result.extra.get("state_snapshot")
                session.runnable = runnable
                session.approval_request = result.extra.get("approval_request")
                _log.info(
                    "run_paused_for_input",
                    hop="H2",
                    run_id=session.run_id,
                    approval_type=session.approval_request.get("type")
                    if session.approval_request
                    else None,
                )
                return
            success = True
    except asyncio.CancelledError:
        session.cancel_requested = True
        raise
    except Exception as exc:
        session.error = sanitize_error(f"{type(exc).__name__}: {exc}")
    finally:
        if session.status == RunStatus.WAITING_INPUT:
            registry.mark_paused(session)
        else:
            await finalize(session, registry, workspace_ref[0], success)


async def resume_run(session: RunSession, registry: RunRegistry, answer: str) -> None:
    """HIL resume. Same finalize as execute. Must not close tail while waiting."""
    success = False
    try:
        result = await session.runnable.resume(session.snapshot, input=answer)
        if result.status == TaskStatus.INPUT_REQUIRED:
            session.status = RunStatus.WAITING_INPUT
            session.snapshot = result.extra.get("state_snapshot")
            session.approval_request = result.extra.get("approval_request")
            registry.mark_paused(session)
            return
        success = True
    except asyncio.CancelledError:
        session.cancel_requested = True
        raise
    except Exception as exc:
        session.error = sanitize_error(f"{type(exc).__name__}: {exc}")
    await finalize(session, registry, None, success)


async def finalize(
    session: RunSession,
    registry: RunRegistry,
    workspace: Any,
    success: bool,
) -> None:
    """The only teardown. Nested finally. HIL must not call this."""
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
            _write_terminal_status(session, success)
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


def _write_terminal_status(session: RunSession, success: bool) -> None:
    if session.cancel_requested:
        session.status = RunStatus.CANCELED
    elif session.error:
        session.status = RunStatus.FAILED
    elif success:
        session.status = RunStatus.COMPLETED
    if session.status in {RunStatus.CANCELED, RunStatus.FAILED, RunStatus.COMPLETED}:
        session.closed_at = time.time()


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
        hub.journal.record(
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
