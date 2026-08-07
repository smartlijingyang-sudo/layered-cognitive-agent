"""Starlette 观测网关 —— POST 建 run、GET SSE 订阅（薄 HTTP 面）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from gateway.run_executor import create_run_session, llm_status, schedule_run
from gateway.run_registry import RunRegistry

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Last-Event-ID",
    "Access-Control-Expose-Headers": "Content-Type",
}

_registry = RunRegistry()


def get_registry() -> RunRegistry:
    return _registry


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
    mode = str(body.get("mode", "board")).strip() or "board"
    track = body.get("track")
    track_str = str(track).strip() if track is not None else None

    session = create_run_session(_registry, question=question, mode=mode)
    schedule_run(_registry, session, track=track_str)
    return JSONResponse(
        {"run_id": session.run_id, "trace_id": session.trace_id},
        status_code=201,
        headers=CORS_HEADERS,
    )


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
    status = llm_status()
    return JSONResponse({"status": "ok", **status}, headers=CORS_HEADERS)


def create_app(registry: RunRegistry | None = None) -> Starlette:
    """工厂：测试可注入独立 RunRegistry。"""
    global _registry
    if registry is not None:
        _registry = registry
    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/runs", create_run, methods=["POST", "OPTIONS"]),
            Route("/runs/{run_id}", get_run, methods=["GET"]),
            Route("/runs/{run_id}/events", stream_events, methods=["GET"]),
            Route("/runs", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/events", _options, methods=["OPTIONS"]),
        ],
    )


app = create_app()
