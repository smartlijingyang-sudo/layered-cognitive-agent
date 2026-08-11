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
from urllib.parse import quote

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from gateway.conversation_store import ConversationStore
from gateway.llm_resolver import LLMResolver, ProductionLLMResolver
from gateway.mode_catalog import DEFAULT_MODE
from gateway.openai_compat_api import (
    chat_completions,
    embeddings_create,
    list_models,
    responses_create,
)
from gateway.run_executor import (
    create_run_session,
    llm_status,
    schedule_run,
    set_llm_resolver,
)
from gateway.run_prompt import compose_run_question
from gateway.run_registry import RunRegistry, RunSession, RunStatus
from gateway.settings import gateway_settings
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.layer0_infra.file_store import (
    LocalFileStore,
    get_default_file_store,
    set_default_file_store,
)


def _cors() -> dict[str, str]:
    """CORS response headers from gateway settings."""
    return gateway_settings().cors_headers_dict()


def _content_disposition(disposition_type: str, filename: str) -> str:
    """Build Content-Disposition header safe for non-ASCII filenames (RFC 5987)."""
    ascii_name = filename.encode("ascii", "replace").decode("ascii")
    encoded = quote(filename, safe="")
    return f"{disposition_type}; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


_registry = RunRegistry()
_conversations = ConversationStore()
_file_store = get_default_file_store()


def get_registry() -> RunRegistry:
    return _registry


def get_conversation_store() -> ConversationStore:
    return _conversations


def get_file_store() -> LocalFileStore:
    return _file_store


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=_cors())


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


async def create_run(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400, headers=_cors())
    question = str(body.get("question", "")).strip()
    if not question:
        return JSONResponse({"error": "question is required"}, status_code=400, headers=_cors())
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
            headers=_cors(),
        )

    if not llm_status()["llm_available"]:
        return JSONResponse(
            {
                "error": "llm_unavailable",
                "detail": "LLM_API_KEY 未配置，无法创建 run。",
            },
            status_code=503,
            headers=_cors(),
        )

    effective_question = compose_run_question(
        question,
        tuple(attachment_ids),
        _file_store,
    )
    session = create_run_session(
        _registry,
        question=effective_question,
        user_text=question,
        mode=mode,
        attachment_ids=attachment_ids,
    )
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
        headers=_cors(),
    )


async def cancel_run(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    session = _registry.get(run_id)
    if session is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=_cors())
    if session.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED):
        return JSONResponse({"status": session.status.value}, headers=_cors())
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
    return JSONResponse({"status": RunStatus.CANCELED.value}, headers=_cors())


async def answer_run(request: Request) -> JSONResponse:
    """Submit a human answer for a paused (WAITING_INPUT) run — HIL resume."""
    run_id = request.path_params["run_id"]
    session = _registry.get(run_id)
    if session is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=_cors())
    if session.status != RunStatus.WAITING_INPUT:
        return JSONResponse(
            {"error": "run not waiting for input", "status": session.status.value},
            status_code=409,
            headers=_cors(),
        )
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400, headers=_cors())
    answer = str(body.get("answer", "")).strip()
    if not answer:
        return JSONResponse({"error": "answer is required"}, status_code=400, headers=_cors())
    if session.snapshot is None or session.runnable is None:
        return JSONResponse(
            {"error": "no resume state available"},
            status_code=500,
            headers=_cors(),
        )
    session.status = RunStatus.RUNNING
    task = asyncio.create_task(_resume_run(session, answer))
    session.task = task
    return JSONResponse(
        {"run_id": run_id, "status": "resumed"},
        headers=_cors(),
    )


async def _resume_run(session: RunSession, answer: str) -> None:
    """Background task: resume a paused run with the human's answer."""

    try:
        result = await session.runnable.resume(session.snapshot, input=answer)
        if result.status == TaskStatus.INPUT_REQUIRED:
            session.status = RunStatus.WAITING_INPUT
            session.snapshot = result.extra.get("state_snapshot")
            session.approval_request = result.extra.get("approval_request")
            _registry.mark_paused(session)
        else:
            session.status = RunStatus.CANCELED if session.cancel_requested else RunStatus.COMPLETED
    except asyncio.CancelledError:
        session.status = RunStatus.CANCELED
        raise
    except Exception as exc:
        session.status = RunStatus.FAILED
        session.error = f"{type(exc).__name__}: {exc}"
    finally:
        if session.status != RunStatus.WAITING_INPUT:
            from lca.layer0_infra.tools.run_finalizer import finalize_run

            await finalize_run(session.run_id)
            session.hub.close()
            session.emit(None)
            _registry.clear_inflight(session)


async def get_run(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    summary = _registry.summary(run_id)
    if summary is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=_cors())
    return JSONResponse(summary, headers=_cors())


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
            **_cors(),
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", **llm_status()}, headers=_cors())


async def create_conversation(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    title = str(body.get("title", "")).strip()
    record = _conversations.create_conversation(title=title)
    return JSONResponse(record, status_code=201, headers=_cors())


async def list_conversations(_request: Request) -> JSONResponse:
    return JSONResponse({"conversations": _conversations.list_conversations()}, headers=_cors())


async def get_conversation(request: Request) -> JSONResponse:
    conversation_id = request.path_params["conversation_id"]
    record = _conversations.get_conversation(conversation_id)
    if record is None:
        return JSONResponse({"error": "conversation not found"}, status_code=404, headers=_cors())
    return JSONResponse(record, headers=_cors())


async def add_conversation_turn(request: Request) -> JSONResponse:
    conversation_id = request.path_params["conversation_id"]
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400, headers=_cors())
    turn = _conversations.add_turn(
        conversation_id,
        run_id=str(body.get("run_id", "")),
        trace_id=str(body.get("trace_id", "")),
        question=str(body.get("question", "")),
        mode=str(body.get("mode", DEFAULT_MODE)),
        status=str(body.get("status", RunStatus.PENDING.value)),
    )
    if turn is None:
        return JSONResponse({"error": "conversation not found"}, status_code=404, headers=_cors())
    return JSONResponse(turn, status_code=201, headers=_cors())


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
        return JSONResponse({"error": "file is required"}, status_code=400, headers=_cors())

    filename = getattr(upload, "filename", None) or "upload.bin"
    content_type = getattr(upload, "content_type", None) or "application/octet-stream"
    read = getattr(upload, "read", None)
    if read is None:
        return JSONResponse({"error": "invalid file field"}, status_code=400, headers=_cors())
    data = await read()
    if not isinstance(data, (bytes, bytearray)):
        return JSONResponse({"error": "invalid file bytes"}, status_code=400, headers=_cors())
    data_bytes = bytes(data)
    if len(data_bytes) == 0:
        return JSONResponse({"error": "empty file"}, status_code=400, headers=_cors())
    max_upload = gateway_settings().max_upload_bytes
    if len(data_bytes) > max_upload:
        return JSONResponse(
            {"error": "file too large", "detail": f"max {max_upload} bytes"},
            status_code=413,
            headers=_cors(),
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
        headers=_cors(),
    )


async def download_file(request: Request) -> Response:
    attachment_id = request.path_params["attachment_id"]
    meta = _file_store.get(attachment_id)
    data = _file_store.read_bytes(attachment_id)
    if meta is None or data is None:
        return JSONResponse({"error": "file not found"}, status_code=404, headers=_cors())

    # Inline for in-app preview (iframe / <img> / markdown fetch). Prefer
    # preview=1; images always inline so thumbnails work without query.
    want_inline = request.query_params.get("preview") == "1" or meta.mime_type.lower().startswith(
        "image/"
    )
    if want_inline and (meta.previewable or meta.mime_type.lower().startswith("image/")):
        return Response(
            content=data,
            media_type=meta.mime_type,
            headers={
                **_cors(),
                "Content-Disposition": _content_disposition("inline", meta.name),
                "Content-Length": str(len(data)),
                "Cache-Control": "private, max-age=3600",
            },
        )

    return Response(
        content=data,
        media_type=meta.mime_type,
        headers={
            **_cors(),
            "Content-Disposition": _content_disposition("attachment", meta.name),
            "Content-Length": str(len(data)),
        },
    )


async def get_file_meta(request: Request) -> JSONResponse:
    attachment_id = request.path_params["attachment_id"]
    meta = _file_store.get(attachment_id)
    if meta is None:
        return JSONResponse({"error": "file not found"}, status_code=404, headers=_cors())
    return JSONResponse(
        {
            "attachment_id": meta.attachment_id,
            "name": meta.name,
            "mime_type": meta.mime_type,
            "url": meta.url,
            "size_bytes": meta.size_bytes,
            "previewable": meta.previewable,
        },
        headers=_cors(),
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
    from gateway._deps import set_deps

    set_deps(registry=_registry, file_store=_file_store)
    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/runs", create_run, methods=["POST", "OPTIONS"]),
            Route("/runs/{run_id}", get_run, methods=["GET"]),
            Route("/runs/{run_id}/cancel", cancel_run, methods=["POST", "OPTIONS"]),
            Route("/runs/{run_id}/answer", answer_run, methods=["POST", "OPTIONS"]),
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
            # LobeHub G2A OpenAI-compatible surface
            Route("/v1/models", list_models, methods=["GET", "OPTIONS"]),
            Route("/v1/chat/completions", chat_completions, methods=["POST", "OPTIONS"]),
            Route("/v1/embeddings", embeddings_create, methods=["POST", "OPTIONS"]),
            Route("/v1/responses", responses_create, methods=["POST", "OPTIONS"]),
            Route("/runs", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/events", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/cancel", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/answer", _options, methods=["OPTIONS"]),
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
