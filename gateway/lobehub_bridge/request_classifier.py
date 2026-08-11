"""Classify LobeHub OpenAI chat payloads for gateway routing."""

from __future__ import annotations

from typing import Any, Literal

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


def _message_text(content: Any) -> str:
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
    """Detect LobeHub system-agent auxiliary calls that should bypass LCA runs."""
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).lower()
        text = _message_text(item.get("content")).lower()
        if not text:
            continue
        if role == "system" and any(marker in text for marker in _TITLE_SYSTEM_MARKERS):
            return "title"
        if role == "user" and any(marker in text for marker in _TITLE_USER_MARKERS):
            return "title"
    return "main"
