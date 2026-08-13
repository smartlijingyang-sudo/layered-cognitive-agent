"""Starlette HTTP 网关 — 薄组合根。

职责：路由注册 + 全局单例（RunRegistry / FileStore）。
所有业务逻辑在子模块（timeline/、openai_compat_api.py、lobehub_bridge/）。
"""

from __future__ import annotations

import asyncio
import contextlib
from urllib.parse import quote

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from gateway._http import CORS_HEADERS
from gateway.openai_compat_api import (
    chat_completions,
    embeddings_create,
    list_models,
    responses_create,
)
from gateway.run_executor import (
    _active_hubs,
    _finalize_run,
    llm_status,
    set_llm_resolver,
)
from gateway.run_registry import RunRegistry, RunSession, RunStatus
from gateway.timeline.routes import create_agent_run, stream_agent_timeline
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.layer0_infra.file_store import (
    LocalFileStore,
    get_default_file_store,
    set_default_file_store,
)
from lca.layer0_infra.llm_resolver import LLMResolver, ProductionLLMResolver

_registry = RunRegistry()
_file_store = get_default_file_store()


def get_registry() -> RunRegistry:
    return _registry


def get_file_store() -> LocalFileStore:
    return _file_store


# ── HTTP helpers ──────────────────────────────────────────


def _content_disposition(disposition_type: str, filename: str) -> str:
    """Build Content-Disposition header safe for non-ASCII filenames (RFC 5987)."""
    ascii_name = filename.encode("ascii", "replace").decode("ascii")
    encoded = quote(filename, safe="")
    return f"{disposition_type}; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


# ── Run 操作 ──────────────────────────────────────────────


async def get_run(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    summary = _registry.summary(run_id)
    if summary is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=CORS_HEADERS)
    return JSONResponse(summary, headers=CORS_HEADERS)


async def cancel_run(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    session = _registry.get(run_id)
    if session is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=CORS_HEADERS)
    if session.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED):
        return JSONResponse({"status": session.status.value}, headers=CORS_HEADERS)
    session.cancel_requested = True
    session.status = RunStatus.CANCELED
    if session.task is not None and not session.task.done():
        session.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await session.task
    return JSONResponse({"status": RunStatus.CANCELED.value}, headers=CORS_HEADERS)


async def answer_run(request: Request) -> JSONResponse:
    """Submit a human answer for a paused (WAITING_INPUT) run — HIL resume."""
    run_id = request.path_params["run_id"]
    session = _registry.get(run_id)
    if session is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=CORS_HEADERS)
    if session.status != RunStatus.WAITING_INPUT:
        return JSONResponse(
            {"error": "run not waiting for input", "status": session.status.value},
            status_code=409,
            headers=CORS_HEADERS,
        )
    import json

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400, headers=CORS_HEADERS)
    answer = str(body.get("answer", "")).strip()
    if not answer:
        return JSONResponse({"error": "answer is required"}, status_code=400, headers=CORS_HEADERS)
    if session.snapshot is None or session.runnable is None:
        return JSONResponse(
            {"error": "no resume state available"},
            status_code=500,
            headers=CORS_HEADERS,
        )
    session.status = RunStatus.RUNNING
    task = asyncio.create_task(_resume_run(session, answer))
    session.task = task
    return JSONResponse(
        {"run_id": run_id, "status": "resumed"},
        headers=CORS_HEADERS,
    )


async def _resume_run(session: RunSession, answer: str) -> None:
    """Background task: resume a paused run with the human's answer."""
    success = False
    try:
        result = await session.runnable.resume(session.snapshot, input=answer)
        if result.status == TaskStatus.INPUT_REQUIRED:
            session.status = RunStatus.WAITING_INPUT
            session.snapshot = result.extra.get("state_snapshot")
            session.approval_request = result.extra.get("approval_request")
            _registry.mark_paused(session)
        else:
            success = True
            session.status = RunStatus.CANCELED if session.cancel_requested else RunStatus.COMPLETED
    except asyncio.CancelledError:
        session.cancel_requested = True
        raise
    except Exception as exc:
        session.status = RunStatus.FAILED
        session.error = f"{type(exc).__name__}: {exc}"
    finally:
        if session.status != RunStatus.WAITING_INPUT:
            await _finalize_run(session, _registry, _active_hubs.get(session.run_id), None, success)


# ── 文件服务 ──────────────────────────────────────────────


async def download_file(request: Request) -> Response:
    attachment_id = request.path_params["attachment_id"]
    meta = _file_store.get(attachment_id)
    data = _file_store.read_bytes(attachment_id)
    if meta is None or data is None:
        return JSONResponse({"error": "file not found"}, status_code=404, headers=CORS_HEADERS)

    want_inline = request.query_params.get("preview") == "1" or meta.mime_type.lower().startswith(
        "image/"
    )
    if want_inline and (meta.previewable or meta.mime_type.lower().startswith("image/")):
        return Response(
            content=data,
            media_type=meta.mime_type,
            headers={
                **CORS_HEADERS,
                "Content-Disposition": _content_disposition("inline", meta.name),
                "Content-Length": str(len(data)),
                "Cache-Control": "private, max-age=3600",
            },
        )

    return Response(
        content=data,
        media_type=meta.mime_type,
        headers={
            **CORS_HEADERS,
            "Content-Disposition": _content_disposition("attachment", meta.name),
            "Content-Length": str(len(data)),
        },
    )


async def get_file_meta(request: Request) -> JSONResponse:
    attachment_id = request.path_params["attachment_id"]
    meta = _file_store.get(attachment_id)
    if meta is None:
        return JSONResponse({"error": "file not found"}, status_code=404, headers=CORS_HEADERS)
    return JSONResponse(
        {
            "attachment_id": meta.attachment_id,
            "name": meta.name,
            "mime_type": meta.mime_type,
            "url": meta.url,
            "size_bytes": meta.size_bytes,
            "previewable": meta.previewable,
        },
        headers=CORS_HEADERS,
    )


# ── 健康检查 ──────────────────────────────────────────────


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", **llm_status()}, headers=CORS_HEADERS)


# ── 组合根 ────────────────────────────────────────────────


def create_app(
    registry: RunRegistry | None = None,
    llm_resolver: LLMResolver | None = None,
    file_store: LocalFileStore | None = None,
) -> Starlette:
    """工厂：测试可注入独立 RunRegistry / LLMResolver / FileStore。"""
    global _registry, _file_store
    if registry is not None:
        _registry = registry
    if file_store is not None:
        _file_store = file_store
        set_default_file_store(file_store)
    if llm_resolver is not None:
        set_llm_resolver(llm_resolver)
    else:
        set_llm_resolver(ProductionLLMResolver())
    return Starlette(
        routes=[
            # 健康
            Route("/health", health, methods=["GET"]),
            # Run 操作
            Route("/runs/{run_id}", get_run, methods=["GET"]),
            Route("/runs/{run_id}/cancel", cancel_run, methods=["POST", "OPTIONS"]),
            Route("/runs/{run_id}/answer", answer_run, methods=["POST", "OPTIONS"]),
            # 文件
            Route("/files/{attachment_id}", download_file, methods=["GET"]),
            Route("/files/{attachment_id}/meta", get_file_meta, methods=["GET"]),
            # OpenAI 兼容
            Route("/v1/models", list_models, methods=["GET", "OPTIONS"]),
            Route("/v1/chat/completions", chat_completions, methods=["POST", "OPTIONS"]),
            Route("/v1/embeddings", embeddings_create, methods=["POST", "OPTIONS"]),
            Route("/v1/responses", responses_create, methods=["POST", "OPTIONS"]),
            # Agent Timeline（生产路径）
            Route("/v1/agent/runs", create_agent_run, methods=["POST", "OPTIONS"]),
            Route(
                "/v1/agent/runs/{run_id}/timeline",
                stream_agent_timeline,
                methods=["GET", "OPTIONS"],
            ),
            # CORS preflight
            Route("/runs/{run_id}/cancel", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/answer", _options, methods=["OPTIONS"]),
        ],
    )


app = create_app()
