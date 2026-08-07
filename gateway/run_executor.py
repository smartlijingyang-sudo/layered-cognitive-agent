"""后台 run 执行器 —— 组装 hub（SSE + jsonl）并驱动 Team/Agent。"""

from __future__ import annotations

import asyncio
from typing import Any

from gateway.collector import GatewayCollector
from gateway.llm_resolver import LLMResolver, ProductionLLMResolver
from gateway.mode_catalog import AUTO_MODE_KEY, DEFAULT_MODE
from gateway.run_registry import RunRegistry, RunSession, RunStatus
from gateway.team_factory import build_runnable, build_runnable_auto
from lca.contracts.atoms.ids import new_id
from lca.layer4_app.api import Agent, Team

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
        session.hub.close()
        session.emit(None)


def create_run_session(
    registry: RunRegistry,
    *,
    question: str,
    mode: str = DEFAULT_MODE,
) -> RunSession:
    """登记新 run 并装配 ObservabilityHub（SSE 广播 + jsonl 落盘）。"""
    run_id = new_id("run")
    trace_id = new_id("trace")
    jsonl_path = registry.jsonl_path_for(run_id)

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
