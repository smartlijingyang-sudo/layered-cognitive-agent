"""后台 run 执行器 —— 组装 hub（SSE + jsonl）并驱动 Team/Agent。"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from gateway.collector import GatewayCollector
from gateway.run_registry import RunRegistry, RunSession, RunStatus
from lca.contracts.atoms.ids import new_id
from lca.contracts.protocols import LLMAdapter
from lca.layer0_infra.llm_adapter import load_dotenv_if_present, resolve_llm_adapter

_DEFAULT_MODE = "board"
_SCRIPTED_TRACK = "scripted"
_REAL_TRACK = "real"


def _llm_credentials() -> tuple[str | None, str | None, str | None]:
    """LLM_API_KEY 优先；兼容 CCS / Cursor 注入的 ANTHROPIC_* 变量。"""
    load_dotenv_if_present()
    key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    base = os.getenv("LLM_BASE_URL") or os.getenv("ANTHROPIC_BASE_URL")
    model = os.getenv("LLM_MODEL") or os.getenv("ANTHROPIC_MODEL")
    return key, base, model


def resolve_llm(*, mode: str = _DEFAULT_MODE, track: str | None = None) -> LLMAdapter:
    """无 track / track=auto：有 API Key 用真实 LLM，否则 scripted。"""
    key, base, model = _llm_credentials()
    if track == _REAL_TRACK:
        if not key:
            raise RuntimeError("LLM_API_KEY 未配置，无法使用真实 LLM")
        return resolve_llm_adapter(api_key=key, base_url=base, model=model)
    if track == _SCRIPTED_TRACK or not key:
        from tests.harness.modes import scripted_llm_for_mode

        return scripted_llm_for_mode(mode)
    return resolve_llm_adapter(api_key=key, base_url=base, model=model)


def llm_status() -> dict[str, str | bool]:
    key, _, _ = _llm_credentials()
    available = bool(key)
    return {
        "llm_available": available,
        "default_track": _REAL_TRACK if available else _SCRIPTED_TRACK,
    }


async def execute_run(
    registry: RunRegistry,
    *,
    run_id: str,
    question: str,
    mode: str = _DEFAULT_MODE,
    track: str | None = None,
) -> None:
    """在后台 task 中执行一次 team run，事件经 SSE + jsonl 双投影。"""
    session = registry.get(run_id)
    if session is None:
        return
    session.status = RunStatus.RUNNING
    try:
        llm = resolve_llm(mode=mode, track=track)
        from tests.harness.runner import run_mode

        await run_mode(mode, llm, collector=session.hub, objective=question)
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
    mode: str = _DEFAULT_MODE,
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
    *,
    track: str | None = None,
) -> asyncio.Task[Any]:
    """fire-and-forget 后台执行；task 强引用存入 session 以支持取消与 GC 安全。"""
    task = asyncio.create_task(
        execute_run(
            registry,
            run_id=session.run_id,
            question=session.question,
            mode=session.mode,
            track=track,
        )
    )
    session.task = task
    return task
