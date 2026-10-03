"""Project Body tool Observations onto OpenAI-shaped model-visible messages (ADR-0201)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from lca.contracts.models.core.execution.decision import Observation

# Align with provider wire limits; fold / token meter may further compact.
_TOOL_RESULT_CONTENT_MAX = 16_000

_CONTENT_KEYS = ("content", "text", "summary", "output", "stdout", "stderr")


def clip_tool_result_content(text: str, *, limit: int = _TOOL_RESULT_CONTENT_MAX) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit] + "\n…(truncated)"


def observation_tool_result_content(observation: Observation | None) -> str:
    """Extract user/model-visible text from one tool Observation."""
    if observation is None:
        return ""
    if not observation.success:
        return clip_tool_result_content(
            (observation.error or "tool failed").strip() or "tool failed"
        )
    payload = observation.payload
    if payload is None:
        return ""
    if isinstance(payload, str):
        return clip_tool_result_content(payload)
    if not isinstance(payload, dict):
        return clip_tool_result_content(json.dumps(payload, ensure_ascii=False, default=str))
    for key in _CONTENT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return clip_tool_result_content(value)
    slim = {key: value for key, value in payload.items() if key != "state"}
    if not slim:
        return ""
    return clip_tool_result_content(json.dumps(slim, ensure_ascii=False, default=str))


def tool_error_text(error: Mapping[str, Any] | None) -> str:
    """Render a ToolError dict into model-visible text.

    Shared projection so ``derive_event_message`` and ``_tool_result_content``
    show the same failure text. A failed tool call must surface its error
    even when the raw content is empty or carries only a source marker;
    otherwise the model sees an empty success and blindly retries
    (run_f70ccf932e9d: 24 ``send_message`` re-asks on a deferred-namespace
    block that never reached the model).
    """
    if not error:
        return ""
    kind = str(error.get("kind") or "execution")
    message = str(error.get("message") or "").strip() or "unknown error"
    retryable = bool(error.get("retryable"))
    return f"[tool_error kind={kind} retryable={retryable}] {message}"


def build_openai_tool_result_message(
    *,
    tool_call_id: str,
    content: str,
    error: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Wire message dict consumed by ``derive_event_message`` and OpenAI history."""
    call_id = tool_call_id.strip()
    err_text = tool_error_text(error)
    text = f"{content}\n{err_text}" if content and err_text else (err_text or content)
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": text,
    }


def build_tool_surface_data(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int,
    outcome: str,
    observation: Observation | None,
    latency_ms: int | None = None,
    ok: bool | None = None,
) -> dict[str, Any]:
    """Session surface payload for ``SURFACE_TOOL_RESULT_TYPE`` append.

    ``ok`` 与 ``outcome`` 一致:outcome="success" 对应 True,其他 False。
    第一性原则:成败字段不允许默认 True(spine.yaml 已声明 ``ok: bool``),
    fold binding 据此与 step.tool_result.record 互相对账。
    """
    content = observation_tool_result_content(observation)
    if ok is None:
        ok = outcome == "success"
    data: dict[str, Any] = {
        "tool_name": tool_name,
        "invocation_id": invocation_id,
        "attempt": attempt,
        "outcome": outcome,
        "ok": ok,
        "message": build_openai_tool_result_message(
            tool_call_id=invocation_id,
            content=content,
        ),
    }
    if latency_ms is not None:
        data["latency_ms"] = latency_ms
    if observation is not None and not observation.success:
        data["error"] = observation.error or outcome
    return data


__all__ = [
    "build_openai_tool_result_message",
    "build_tool_surface_data",
    "clip_tool_result_content",
    "observation_tool_result_content",
]
