"""Direct structured LLM calls for OpenAI Responses / json_schema compatibility."""

from __future__ import annotations

import json
import time
from typing import Any

from lca.contracts.atoms.ids import new_id
from lca.layer0_infra.llm_adapter.settings import is_qwen_model
from lca.layer0_infra.llm_resolver import (
    get_async_openai_client,
    get_model_registry,
    llm_credentials,
)


class StructuredLLMError(RuntimeError):
    """Upstream structured LLM call failed."""


_RESPONSES_OBJECT = "response"


def normalize_responses_input(raw_input: Any) -> list[dict[str, Any]]:
    """Map OpenAI Responses ``input`` to chat ``messages``."""
    if isinstance(raw_input, str):
        text = raw_input.strip()
        if not text:
            return []
        return [{"role": "user", "content": text}]
    if not isinstance(raw_input, list):
        return []

    messages: list[dict[str, Any]] = []
    for item in raw_input:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in {"system", "user", "assistant", "developer"}:
            continue
        content = item.get("content")
        if isinstance(content, str):
            text = content.strip()
            if text:
                messages.append({"role": role, "content": text})
        elif isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    text = str(part.get("text", "")).strip()
                    if text:
                        parts.append(text)
            if parts:
                messages.append({"role": role, "content": "\n".join(parts)})
    return messages


def extract_json_schema_format(body: dict[str, Any]) -> dict[str, Any] | None:
    """Extract ``response_format`` payload from Responses API body."""
    text = body.get("text")
    if not isinstance(text, dict):
        return None
    fmt = text.get("format")
    if not isinstance(fmt, dict):
        return None
    if fmt.get("type") != "json_schema":
        return None
    schema_body = {key: value for key, value in fmt.items() if key not in {"type", "strict"}}
    if not schema_body:
        return None
    return {"type": "json_schema", "json_schema": schema_body}


def resolve_upstream_model(requested_model: str) -> str:
    """LCA modes map to configured ``LLM_MODEL``; others pass through.

    委托给 ``ModelRegistry`` —— 单一事实源，不再本地维护别名 dict。
    """
    return get_model_registry().resolve_chat_model(requested_model)


def resolve_embedding_model(requested_model: str) -> str:
    """Map OpenAI embedding model names to upstream-compatible ids.

    委托给 ``ModelRegistry``。
    """
    return get_model_registry().resolve_embedding_model(requested_model)


async def create_embeddings(
    *,
    model: str,
    raw_input: Any,
    dimensions: Any = None,
    encoding_format: Any = None,
) -> dict[str, Any]:
    """Proxy embeddings to upstream OpenAI-compatible API."""
    key, _, _ = llm_credentials()
    if not key:
        raise StructuredLLMError("LLM_API_KEY 未配置")

    upstream_model = resolve_upstream_model(model)
    client = get_async_openai_client()
    kwargs: dict[str, Any] = {"model": upstream_model, "input": raw_input}
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    if encoding_format is not None:
        kwargs["encoding_format"] = encoding_format

    response = await client.embeddings.create(**kwargs)
    data = [
        {
            "object": "embedding",
            "index": item.index,
            "embedding": item.embedding,
        }
        for item in response.data
    ]
    usage_raw = getattr(response, "usage", None)
    usage: dict[str, Any] | None = None
    if usage_raw is not None:
        usage = {
            "prompt_tokens": getattr(usage_raw, "prompt_tokens", 0) or 0,
            "total_tokens": getattr(usage_raw, "total_tokens", 0) or 0,
        }
    payload: dict[str, Any] = {
        "object": "list",
        "data": data,
        "model": upstream_model,
    }
    if usage is not None:
        payload["usage"] = usage
    return payload


async def create_simple_completion(
    *,
    messages: list[dict[str, Any]],
    model: str,
) -> tuple[str, dict[str, Any] | None]:
    """Direct upstream chat completion — no LCA agent loop."""
    key, _, _ = llm_credentials()
    if not key:
        raise StructuredLLMError("LLM_API_KEY 未配置")

    upstream_model = resolve_upstream_model(model)
    client = get_async_openai_client()
    req_messages: Any = messages
    response = await client.chat.completions.create(
        model=upstream_model,
        messages=req_messages,
    )
    choice = response.choices[0]
    text = choice.message.content or ""
    usage_raw = getattr(response, "usage", None)
    usage: dict[str, Any] | None = None
    if usage_raw is not None:
        usage = {
            "prompt_tokens": getattr(usage_raw, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage_raw, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage_raw, "total_tokens", 0) or 0,
        }
    return text, usage


async def create_structured_completion(
    *,
    messages: list[dict[str, Any]],
    model: str,
    response_format: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    """Call upstream OpenAI-compatible chat completions with json_schema output."""
    key, _, _ = llm_credentials()
    if not key:
        raise StructuredLLMError("LLM_API_KEY 未配置")

    from openai import APIError

    upstream_model = resolve_upstream_model(model)
    client = get_async_openai_client()
    req_messages: Any = list(messages)
    req_format: Any = response_format
    try:
        response = await client.chat.completions.create(
            model=upstream_model,
            messages=req_messages,
            response_format=req_format,
        )
    except APIError:
        if not is_qwen_model(upstream_model):
            raise
        schema_hint = json.dumps(
            response_format.get("json_schema", response_format),
            ensure_ascii=False,
        )
        fallback_messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    f"Respond with a single JSON object only, no markdown. Schema: {schema_hint}"
                ),
            },
            *req_messages,
        ]
        response = await client.chat.completions.create(
            model=upstream_model,
            messages=fallback_messages,
            response_format={"type": "json_object"},
        )
    choice = response.choices[0]
    text = choice.message.content or ""
    usage_raw = getattr(response, "usage", None)
    usage: dict[str, Any] | None = None
    if usage_raw is not None:
        usage = {
            "input_tokens": getattr(usage_raw, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage_raw, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage_raw, "total_tokens", 0) or 0,
        }
    return text, usage


def build_responses_payload(
    *,
    model: str,
    output_text: str,
    usage: dict[str, Any] | None,
) -> dict[str, Any]:
    """Minimal OpenAI Responses object consumed by LobeHub ``generateObject``."""
    response_id = f"resp_{new_id('resp')}"
    payload: dict[str, Any] = {
        "id": response_id,
        "object": _RESPONSES_OBJECT,
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output_text": output_text,
        "output": [
            {
                "id": f"msg_{new_id('msg')}",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": output_text,
                    }
                ],
            }
        ],
    }
    if usage is not None:
        payload["usage"] = usage
    return payload
