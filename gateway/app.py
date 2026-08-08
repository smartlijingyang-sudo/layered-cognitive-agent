"""Starlette 观测网关 —— POST 建 run、GET SSE 订阅（薄 HTTP 面）。

会话历史：前端读路径为浏览器 IndexedDB；``ConversationStore``（SQLite）与
``/conversations`` 路由为跨设备同步预留，见 ``gateway/conversation_store.py``。

Phase C 文件能力：``POST /conversations/{id}/attachments`` 上传、
``GET /files/{id}`` 下载；CreateRun 可带 ``attachment_ids``。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
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
from lca.layer0_infra.file_store import (
    LocalFileStore,
    get_default_file_store,
    set_default_file_store,
)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Last-Event-ID",
    "Access-Control-Expose-Headers": "Content-Type, Content-Disposition",
}

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_registry = RunRegistry()
_conversations = ConversationStore()
_file_store = get_default_file_store()


def get_registry() -> RunRegistry:
    return _registry


def get_conversation_store() -> ConversationStore:
    return _conversations


def get_file_store() -> LocalFileStore:
    return _file_store  # type: ignore[return-value]


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


def _parse_attachment_ids(body: dict) -> list[str]:
    raw = body.get("attachment_ids") or body.get("attachmentIds") or []
    if not isinstance(raw, list):
        return []
    ids: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text:
            ids.append(text)
    return ids


def _question_with_attachments(question: str, attachment_ids: list[str]) -> str:
    """Embed attachment metadata so agents can cite / read file context."""
    if not attachment_ids:
        return question
    lines = ["[用户附件]"]
    for attachment_id in attachment_ids:
        meta = _file_store.get(attachment_id)
        if meta is None:
            lines.append(f"- (missing) {attachment_id}")
            continue
        lines.append(
            f"- {meta.name} ({meta.mime_type}, {meta.size_bytes} B) url={meta.url} id={meta.attachment_id}"
        )
        preview = (
            _file_store.read_text_preview(attachment_id)
            if isinstance(_file_store, LocalFileStore)
            else None
        )
        if preview:
            lines.append("  preview:")
            for preview_line in preview.splitlines()[:40]:
                lines.append(f"  | {preview_line}")
    lines.append("")
    lines.append(f"用户问题: {question}")
    return "\n".join(lines)


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
    attachment_ids = _parse_attachment_ids(body)

    missing = [aid for aid in attachment_ids if not _file_store.exists(aid)]
    if missing:
        return JSONResponse(
            {
                "error": "unknown_attachment",
                "detail": f"attachment not found: {', '.join(missing)}",
            },
            status_code=400,
            headers=CORS_HEADERS,
        )

    if not llm_status()["llm_available"]:
        return JSONResponse(
            {
                "error": "llm_unavailable",
                "detail": "LLM_API_KEY 未配置，无法创建 run。",
            },
            status_code=503,
            headers=CORS_HEADERS,
        )

    effective_question = _question_with_attachments(question, attachment_ids)
    session = create_run_session(_registry, question=effective_question, mode=mode)
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
        # 等 execute_run 的 finally 收尾（TeamRunFinished + hub.close + emit）。
        # 不可在此 hub.close：attach token 在 run task / 成员 task，此处 detach
        # 会跨 asyncio Context，且 Finished 尚未发射导致 container 泄漏。
        with contextlib.suppress(asyncio.CancelledError):
            await session.task
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


async def upload_attachment(request: Request) -> JSONResponse:
    conversation_id = request.path_params["conversation_id"]
    # Ensure conversation exists (create soft placeholder if frontend only has local id)
    if _conversations.get_conversation(conversation_id) is None:
        # Accept uploads scoped to client-side conversation ids without failing:
        # store still keys files by attachment_id; conversation_id is metadata only.
        pass

    form = await request.form()
    upload = form.get("file")
    if upload is None:
        return JSONResponse({"error": "file is required"}, status_code=400, headers=CORS_HEADERS)

    filename = getattr(upload, "filename", None) or "upload.bin"
    content_type = getattr(upload, "content_type", None) or "application/octet-stream"
    read = getattr(upload, "read", None)
    if read is None:
        return JSONResponse({"error": "invalid file field"}, status_code=400, headers=CORS_HEADERS)
    data = await read()
    if not isinstance(data, (bytes, bytearray)):
        return JSONResponse({"error": "invalid file bytes"}, status_code=400, headers=CORS_HEADERS)
    data_bytes = bytes(data)
    if len(data_bytes) == 0:
        return JSONResponse({"error": "empty file"}, status_code=400, headers=CORS_HEADERS)
    if len(data_bytes) > _MAX_UPLOAD_BYTES:
        return JSONResponse(
            {"error": "file too large", "detail": f"max {_MAX_UPLOAD_BYTES} bytes"},
            status_code=413,
            headers=CORS_HEADERS,
        )

    stored = _file_store.put(
        data=data_bytes,
        name=str(filename),
        mime_type=str(content_type),
        conversation_id=conversation_id,
    )
    return JSONResponse(
        {
            "attachment_id": stored.attachment_id,
            "name": stored.name,
            "mime_type": stored.mime_type,
            "url": stored.url,
            "size_bytes": stored.size_bytes,
        },
        status_code=201,
        headers=CORS_HEADERS,
    )


async def download_file(request: Request) -> Response:
    attachment_id = request.path_params["attachment_id"]
    meta = _file_store.get(attachment_id)
    data = _file_store.read_bytes(attachment_id)
    if meta is None or data is None:
        return JSONResponse({"error": "file not found"}, status_code=404, headers=CORS_HEADERS)

    # Optional HTML preview content for sandboxed iframe (text/html only)
    if request.query_params.get("preview") == "1" and meta.previewable:
        return Response(
            content=data,
            media_type=meta.mime_type,
            headers={
                **CORS_HEADERS,
                "Content-Disposition": f'inline; filename="{meta.name}"',
            },
        )

    return Response(
        content=data,
        media_type=meta.mime_type,
        headers={
            **CORS_HEADERS,
            "Content-Disposition": f'attachment; filename="{meta.name}"',
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


def create_app(
    registry: RunRegistry | None = None,
    conversation_store: ConversationStore | None = None,
    llm_resolver: LLMResolver | None = None,
    file_store: LocalFileStore | None = None,
) -> Starlette:
    """工厂：测试可注入独立 RunRegistry / ConversationStore / LLMResolver / FileStore。"""
    global _registry, _conversations, _file_store
    if registry is not None:
        _registry = registry
    if conversation_store is not None:
        _conversations = conversation_store
    if file_store is not None:
        _file_store = file_store
        set_default_file_store(file_store)
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
            Route(
                "/conversations/{conversation_id}/attachments",
                upload_attachment,
                methods=["POST", "OPTIONS"],
            ),
            Route("/files/{attachment_id}", download_file, methods=["GET"]),
            Route("/files/{attachment_id}/meta", get_file_meta, methods=["GET"]),
            Route("/runs", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/events", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/cancel", _options, methods=["OPTIONS"]),
            Route("/conversations", _options, methods=["OPTIONS"]),
            Route("/conversations/{conversation_id}/turns", _options, methods=["OPTIONS"]),
            Route(
                "/conversations/{conversation_id}/attachments",
                _options,
                methods=["OPTIONS"],
            ),
        ],
    )


app = create_app()
