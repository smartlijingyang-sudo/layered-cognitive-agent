"""后台 run 执行器 —— 组装 hub（SSE + jsonl）并驱动 Team/Agent。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import structlog

from gateway.collector import GatewayCollector
from gateway.llm_resolver import LLMResolver, ProductionLLMResolver
from gateway.mode_catalog import AUTO_MODE_KEY, DEFAULT_MODE
from gateway.run_registry import RunRegistry, RunSession, RunStatus
from gateway.team_factory import build_runnable, build_runnable_auto
from lca.contracts.atoms.ids import new_id
from lca.layer0_infra.file_store import get_default_file_store
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.sandbox.runtime_scope import bind_sandbox_runtime
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
            # 全仓库唯一按 mode 分支处：auto 需先 await 选角，无法并入同步
            # build_runnable 查表路径（ADR-0042）。若未来出现第二个特殊入口，
            # 应重构为 runner 注册表而非继续加分支。
            if mode == AUTO_MODE_KEY:
                runnable = await build_runnable_auto(
                    question,
                    llm,
                    observability=session.hub,
                    trace_id=session.trace_id,
                    run_id=session.run_id,
                )
            else:
                runnable = build_runnable(mode, llm, observability=session.hub)
            await runnable.run(question)
        session.status = RunStatus.CANCELED if session.cancel_requested else RunStatus.COMPLETED
    except asyncio.CancelledError:
        session.status = RunStatus.CANCELED
        session.cancel_requested = True
        raise
    except Exception as exc:
        session.status = RunStatus.FAILED
        session.error = f"{type(exc).__name__}: {exc}"
    finally:
        # Release run-scoped resources (sandbox sessions, …) before closing hub.
        await finalize_run(session.run_id)
        session.hub.close()
        session.emit(None)


def create_run_session(
    registry: RunRegistry,
    *,
    question: str,
    mode: str = DEFAULT_MODE,
    attachment_ids: Sequence[str] = (),
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
        mode=mode,
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
