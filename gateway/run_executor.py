"""后台 run 执行器 —— 组装 hub（SSE + jsonl）并驱动 Team/Agent。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import structlog

from gateway.collector import GatewayCollector
from gateway.llm_resolver import LLMResolver, ProductionLLMResolver
from gateway.mode_catalog import DEFAULT_MODE, SOLO_MODE_KEY
from gateway.run_registry import RunRegistry, RunSession, RunStatus
from gateway.team_factory import build_runnable_team, build_solo_agent
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY, ConversationTurn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.team.run_context import RunContext
from lca.layer0_infra.file_store import get_default_file_store
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.sandbox.runtime_scope import bind_sandbox_runtime
from lca.layer0_infra.search.scope import search_run_scope
from lca.layer0_infra.tools.run_attachment_scope import run_attachment_scope
from lca.layer0_infra.tools.run_finalizer import finalize_run, run_id_scope
from lca.layer0_infra.workspace import run_workspace_scope
from lca.layer4_app.api import Agent, Team

_log = structlog.get_logger(__name__)

_default_llm_resolver: LLMResolver = ProductionLLMResolver()


def get_llm_resolver() -> LLMResolver:
    return _default_llm_resolver


def set_llm_resolver(resolver: LLMResolver) -> None:
    global _default_llm_resolver
    _default_llm_resolver = resolver


def llm_status() -> dict[str, bool]:
    return {"llm_available": get_llm_resolver().is_available()}


async def execute_run(
    registry: RunRegistry,
    *,
    run_id: str,
    question: str,
    mode: str = DEFAULT_MODE,
) -> None:
    """在后台 task 中执行一次 team run，事件经 SSE + jsonl 双投影。"""
    session = registry.get(run_id)
    if session is None:
        return
    session.status = RunStatus.RUNNING
    try:
        # Bind run_id + attachments for the whole task (contextvars copy across create_task).
        with (
            run_id_scope(session.run_id),
            run_attachment_scope(session.attachment_ids),
            run_workspace_scope(session.run_id),
            search_run_scope(),
        ):
            sandbox = resolve_sandbox()
            if sandbox is not None and session.attachment_ids:
                try:
                    runtime = await bind_sandbox_runtime(
                        session.run_id,
                        sandbox,
                        get_default_file_store(),
                        session.attachment_ids,
                    )
                    mount_err = await runtime.ensure_ready()
                    if mount_err is not None:
                        session.status = RunStatus.FAILED
                        session.error = mount_err.error_summary or mount_err.error
                        return
                except Exception as exc:
                    _log.warning(
                        "sandbox_runtime_bind_failed", run_id=session.run_id, error=str(exc)
                    )
            llm = get_llm_resolver().resolve(mode=mode)
            runnable: Agent | Team
            # Solo/Team 分治（ADR-0052）：solo 是裸模型（同步），team 走 LLM casting（异步）。
            # 两种根本不同的构建机制，分支在语义上是稳定的。
            if mode == SOLO_MODE_KEY:
                runnable = build_solo_agent(llm, observability=session.hub)
            else:
                runnable = await build_runnable_team(
                    question,
                    llm,
                    observability=session.hub,
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
                    run_id=session.run_id,
                    approval_type=session.approval_request.get("type")
                    if session.approval_request
                    else None,
                )
                return
        session.status = RunStatus.CANCELED if session.cancel_requested else RunStatus.COMPLETED
    except asyncio.CancelledError:
        session.status = RunStatus.CANCELED
        session.cancel_requested = True
        raise
    except Exception as exc:
        session.status = RunStatus.FAILED
        session.error = f"{type(exc).__name__}: {exc}"
    finally:
        if session.status == RunStatus.WAITING_INPUT:
            # HIL pause: keep session alive for resume, do NOT close hub or emit sentinel.
            registry.mark_paused(session)
        else:
            # Release run-scoped resources (sandbox sessions, …) before closing hub.
            await finalize_run(session.run_id)
            session.hub.close()
            session.emit(None)
            registry.clear_inflight(session)


def _run_context_for_session(session: RunSession) -> RunContext | None:
    if not session.prior_turns:
        return None
    return RunContext(
        extra={
            PRIOR_CONVERSATION_WM_KEY: [
                {"role": t.role, "content": t.content} for t in session.prior_turns
            ]
        }
    )


def create_run_session(
    registry: RunRegistry,
    *,
    question: str,
    user_text: str,
    mode: str = DEFAULT_MODE,
    attachment_ids: Sequence[str] = (),
    prior_turns: Sequence[ConversationTurn] = (),
) -> RunSession:
    """登记新 run 并装配 ObservabilityHub（SSE 广播 + jsonl 落盘）。"""
    run_id = new_id("run")
    trace_id = new_id("trace")
    jsonl_path = registry.jsonl_path_for(run_id)
    cleaned_ids = tuple(str(i).strip() for i in attachment_ids if str(i).strip())

    def _emit(frame: str | None) -> None:
        if session_ref[0] is not None:
            session_ref[0].emit(frame)

    session_ref: list[RunSession | None] = [None]
    hub = GatewayCollector(_emit, jsonl_path)
    session = RunSession(
        run_id=run_id,
        trace_id=trace_id,
        jsonl_path=jsonl_path,
        hub=hub,
        question=question,
        user_text=user_text,
        mode=mode,
        prior_turns=tuple(prior_turns),
        attachment_ids=cleaned_ids,
    )
    session_ref[0] = session
    registry.put(session)
    return session


def schedule_run(
    registry: RunRegistry,
    session: RunSession,
) -> asyncio.Task[Any]:
    """fire-and-forget 后台执行；task 强引用存入 session 以支持取消与 GC 安全。"""
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
