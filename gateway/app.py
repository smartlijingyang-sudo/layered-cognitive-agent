"""Starlette 观测网关 —— POST 建 run、GET SSE 订阅（薄 HTTP 面）。

会话历史：前端读路径为浏览器 IndexedDB；``ConversationStore``（SQLite）与
``/conversations`` 路由为跨设备同步预留，见 ``gateway/conversation_store.py``。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from gateway.conversation_store import ConversationStore
from gateway.llm_resolver import LLMResolver, ProductionLLMResolver
from gateway.mode_catalog import DEFAULT_MODE
from gateway.run_executor import (
    create_run_session,
    llm_status,
    schedule_run,
    set_llm_resolver,
)
from gateway.run_registry import RunRegistry, RunStatus

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Last-Event-ID",
    "Access-Control-Expose-Headers": "Content-Type",
}

_registry = RunRegistry()
_conversations = ConversationStore()


def get_registry() -> RunRegistry:
    return _registry


def get_conversation_store() -> ConversationStore:
    return _conversations


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


async def create_run(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400, headers=CORS_HEADERS)
    question = str(body.get("question", "")).strip()
    if not question:
        return JSONResponse(
            {"error": "question is required"}, status_code=400, headers=CORS_HEADERS
        )
    mode = str(body.get("mode", DEFAULT_MODE)).strip() or DEFAULT_MODE
    conversation_id = body.get("conversation_id")
    conversation_id_str = str(conversation_id).strip() if conversation_id else None

    if not llm_status()["llm_available"]:
        return JSONResponse(
            {
                "error": "llm_unavailable",
                "detail": "LLM_API_KEY 未配置，无法创建 run。",
            },
            status_code=503,
            headers=CORS_HEADERS,
        )

    session = create_run_session(_registry, question=question, mode=mode)
    schedule_run(_registry, session)

    if conversation_id_str:
        _conversations.add_turn(
            conversation_id_str,
            run_id=session.run_id,
            trace_id=session.trace_id,
            question=question,
            mode=mode,
            status=RunStatus.PENDING.value,
        )

    return JSONResponse(
        {"run_id": session.run_id, "trace_id": session.trace_id},
        status_code=201,
        headers=CORS_HEADERS,
    )


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
    session.hub.close()
    session.emit(None)
    _conversations.update_turn_status(run_id, RunStatus.CANCELED.value)
    return JSONResponse({"status": RunStatus.CANCELED.value}, headers=CORS_HEADERS)


async def get_run(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    summary = _registry.summary(run_id)
    if summary is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=CORS_HEADERS)
    return JSONResponse(summary, headers=CORS_HEADERS)


async def stream_events(request: Request) -> StreamingResponse:
    run_id = request.path_params["run_id"]
    last_event_id = request.headers.get("last-event-id")

    async def _generate() -> AsyncIterator[bytes]:
        async for frame in _registry.event_stream(run_id, last_event_id):
            yield frame.encode("utf-8")

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            **CORS_HEADERS,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", **llm_status()}, headers=CORS_HEADERS)


async def create_conversation(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    title = str(body.get("title", "")).strip()
    record = _conversations.create_conversation(title=title)
    return JSONResponse(record, status_code=201, headers=CORS_HEADERS)


async def list_conversations(_request: Request) -> JSONResponse:
    return JSONResponse(
        {"conversations": _conversations.list_conversations()}, headers=CORS_HEADERS
    )


async def get_conversation(request: Request) -> JSONResponse:
    conversation_id = request.path_params["conversation_id"]
    record = _conversations.get_conversation(conversation_id)
    if record is None:
        return JSONResponse(
            {"error": "conversation not found"}, status_code=404, headers=CORS_HEADERS
        )
    return JSONResponse(record, headers=CORS_HEADERS)


async def add_conversation_turn(request: Request) -> JSONResponse:
    conversation_id = request.path_params["conversation_id"]
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400, headers=CORS_HEADERS)
    turn = _conversations.add_turn(
        conversation_id,
        run_id=str(body.get("run_id", "")),
        trace_id=str(body.get("trace_id", "")),
        question=str(body.get("question", "")),
        mode=str(body.get("mode", DEFAULT_MODE)),
        status=str(body.get("status", RunStatus.PENDING.value)),
    )
    if turn is None:
        return JSONResponse(
            {"error": "conversation not found"}, status_code=404, headers=CORS_HEADERS
        )
    return JSONResponse(turn, status_code=201, headers=CORS_HEADERS)


def create_app(
    registry: RunRegistry | None = None,
    conversation_store: ConversationStore | None = None,
    llm_resolver: LLMResolver | None = None,
) -> Starlette:
    """工厂：测试可注入独立 RunRegistry / ConversationStore / LLMResolver。"""
    global _registry, _conversations
    if registry is not None:
        _registry = registry
    if conversation_store is not None:
        _conversations = conversation_store
    if llm_resolver is not None:
        set_llm_resolver(llm_resolver)
    else:
        set_llm_resolver(ProductionLLMResolver())
    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/runs", create_run, methods=["POST", "OPTIONS"]),
            Route("/runs/{run_id}", get_run, methods=["GET"]),
            Route("/runs/{run_id}/cancel", cancel_run, methods=["POST", "OPTIONS"]),
            Route("/runs/{run_id}/events", stream_events, methods=["GET"]),
            Route("/conversations", create_conversation, methods=["POST", "OPTIONS"]),
            Route("/conversations", list_conversations, methods=["GET"]),
            Route("/conversations/{conversation_id}", get_conversation, methods=["GET"]),
            Route(
                "/conversations/{conversation_id}/turns",
                add_conversation_turn,
                methods=["POST", "OPTIONS"],
            ),
            Route("/runs", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/events", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/cancel", _options, methods=["OPTIONS"]),
            Route("/conversations", _options, methods=["OPTIONS"]),
            Route("/conversations/{conversation_id}/turns", _options, methods=["OPTIONS"]),
        ],
    )


app = create_app()
