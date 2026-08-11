"""Shared constants and utilities for OpenAI frame projection.

Extracted from ``journal_openai_projector.py`` to break the 570-line monolith
into focused modules: this file holds pure helpers; ``openai_projector.py``
holds the stateful ``JournalOpenAiProjector``; ``openai_stream.py`` holds
the async streaming adapters.
"""

from __future__ import annotations

import json
from typing import Any, Final

USER_FACING_TERMINAL_ACTIONS: Final[frozenset[str]] = frozenset({"respond", "stop", "ask_human"})
TOOL_RESULT_MAX_LEN: Final[int] = 500
_ALLOWED_FINISH_REASONS: Final[frozenset[str | None]] = frozenset({None, "stop"})


def parse_sse_frame_record(frame: str) -> dict[str, Any] | None:
    """Extract JSON record from a journal SSE frame."""
    for line in frame.splitlines():
        if line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                return None
            return payload if isinstance(payload, dict) else None
    return None


def extract_user_question(messages: list[Any]) -> str:
    """Last user message text from OpenAI-style messages."""
    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        if item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            text = content.strip()
            if text:
                return text
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
                return "\n".join(parts)
    return ""


def resolve_lca_mode(model: str) -> str:
    """Map OpenAI model id → LCA gateway mode."""
    key = model.strip().lower()
    if key in {"team", "auto"}:
        return "team"
    return "solo"


def parse_args_json(raw: str) -> dict[str, Any]:
    """Parse a JSON arguments string into a dict (tolerant of malformed input)."""
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def safe_json_string(raw: str) -> str:
    """Ensure arguments preview is valid JSON string for OpenAI tool_calls delta."""
    raw = (raw or "").strip()
    if not raw:
        return "{}"
    try:
        json.loads(raw)
        return raw
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"preview": raw[:200]})
