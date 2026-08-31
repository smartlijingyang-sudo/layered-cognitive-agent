"""OpenAI-compatible wire primitives for the Gateway housekeeper surface."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from starlette.responses import JSONResponse, StreamingResponse

from lca.cognition.team.modes_catalog import LCA_UI_MODELS
from lca.contracts.atoms.ids import new_id
from lca.plugins.transport.webserver.handlers.cors import cors_headers

OPENAI_CHAT_ID_PREFIX = "chatcmpl-"
LobeHubChatKind = Literal["main", "title"]

_TITLE_SYSTEM_MARKERS = (
    "conversation summarizer",
    "generate a concise title",
)
_TITLE_USER_MARKERS = (
    "<task>",
    "generate a concise title",
    "生成对话标题",
    "生成简洁的标题",
)


def message_text(content: Any) -> str:
    """Extract plain text from either string or OpenAI content-part input."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = str(part.get("text", "")).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def classify_lobehub_chat_request(messages: list[Any]) -> LobeHubChatKind:
    """Classify LobeHub auxiliary title calls that should bypass the Run surface."""
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).lower()
        text = message_text(item.get("content")).lower()
        if not text:
            continue
        if role == "system" and any(marker in text for marker in _TITLE_SYSTEM_MARKERS):
            return "title"
        if role == "user" and any(marker in text for marker in _TITLE_USER_MARKERS):
            return "title"
    return "main"


def lca_models_payload() -> dict[str, Any]:
    """Return the model-list shape expected by OpenAI-compatible clients."""
    data = [
        {"id": key, "object": "model", "created": 0, "owned_by": "lca"} for key in LCA_UI_MODELS
    ]
    return {"object": "list", "data": data}


def new_chat_id() -> str:
    """Create an OpenAI-shaped response identifier for one housekeeper request."""
    return f"{OPENAI_CHAT_ID_PREFIX}{new_id('chat')}"


def error_response(
    message: str,
    *,
    status_code: int,
    error_type: str = "invalid_request_error",
    code: str | None = None,
) -> JSONResponse:
    """Encode a CORS-enabled OpenAI error response."""
    error: dict[str, Any] = {"message": message, "type": error_type}
    if code:
        error["code"] = code
    return JSONResponse({"error": error}, status_code=status_code, headers=cors_headers())


def chat_response(chat_id: str, content: str, usage: dict[str, Any] | None) -> dict[str, Any]:
    """Encode a non-streaming OpenAI Chat Completion success payload."""
    return {
        "id": chat_id,
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": usage or {},
    }


def streaming_chat_response(chat_id: str, content: str) -> StreamingResponse:
    """Encode one complete text response as OpenAI-style server-sent events."""

    async def body() -> AsyncIterator[bytes]:
        chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}}],
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode()
        stop = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(stop, ensure_ascii=False)}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers=cors_headers(**{"Cache-Control": "no-cache"}),
    )


__all__ = [
    "LobeHubChatKind",
    "chat_response",
    "classify_lobehub_chat_request",
    "error_response",
    "lca_models_payload",
    "message_text",
    "new_chat_id",
    "streaming_chat_response",
]
