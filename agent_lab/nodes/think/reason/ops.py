"""reason ops — messages (+ tools) → LLMResponse artifact."""

from __future__ import annotations

import asyncio
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def complete_turn(
    messages_artifact: Artifact | None,
    tools_artifact: Artifact | None,
    *,
    adapter_factory: Any,
    adapter_kwargs: dict[str, Any] | None = None,
) -> Artifact:
    messages = _as_messages(messages_artifact)
    prompt, history = _split_prompt_history(messages)
    tools = _as_tools(tools_artifact)

    adapter = adapter_factory(**dict(adapter_kwargs or {}))
    complete_kwargs: dict[str, Any] = {}
    if history:
        complete_kwargs["history"] = history
    if tools is not None:
        complete_kwargs["tools"] = tools

    response = asyncio.run(adapter.complete(prompt, **complete_kwargs))
    text = getattr(response, "text", "") or ""
    payload: dict[str, Any] = {
        "text": text,
        "content": text,
        "role": "assistant",
        "model": getattr(response, "model", "") or "",
        "tool_calls": _tool_calls_to_dicts(getattr(response, "tool_calls", None) or []),
        "finish_reason": getattr(response, "finish_reason", None),
    }
    usage = getattr(response, "usage", None)
    if usage is not None:
        payload["usage"] = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
        }
    return Artifact(
        kind=ArtifactKind.MESSAGE,
        content=payload,
        schema_ref="llm.response.v1",
    )


def _as_messages(art: Artifact | None) -> list[dict[str, Any]]:
    if art is None:
        return []
    content = art.content
    if isinstance(content, list):
        return [dict(m) for m in content if isinstance(m, dict)]
    if isinstance(content, dict) and isinstance(content.get("messages"), list):
        return [dict(m) for m in content["messages"] if isinstance(m, dict)]
    return []


def _as_tools(art: Artifact | None) -> list[Any] | None:
    if art is None or art.content is None:
        return None
    content = art.content
    if isinstance(content, list):
        return list(content)
    if isinstance(content, dict):
        nested = content.get("tools")
        if isinstance(nested, list):
            return list(nested)
        keys = set(content)
        if keys & {"type", "function", "name"}:
            return [content]
    return None


def _split_prompt_history(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    if not messages:
        return "", []
    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        parts = [
            str(m.get("content", ""))
            for m in messages
            if isinstance(m.get("content"), str) and m.get("content")
        ]
        return "\n".join(parts), []
    prompt = str(messages[last_user_idx].get("content") or "")
    history = messages[:last_user_idx]
    return prompt, history


def _tool_calls_to_dicts(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in raw:
        if isinstance(tc, dict):
            out.append(
                {
                    "id": str(tc.get("id") or tc.get("call_id") or ""),
                    "call_id": str(tc.get("call_id") or tc.get("id") or ""),
                    "name": str(tc.get("name") or tc.get("tool_name") or ""),
                    "arguments": dict(tc.get("arguments") or tc.get("args") or {}),
                }
            )
            continue
        out.append(
            {
                "id": str(getattr(tc, "call_id", "") or getattr(tc, "id", "") or ""),
                "call_id": str(getattr(tc, "call_id", "") or getattr(tc, "id", "") or ""),
                "name": str(getattr(tc, "name", "") or getattr(tc, "tool_name", "") or ""),
                "arguments": dict(getattr(tc, "arguments", {}) or {}),
            }
        )
    return out
