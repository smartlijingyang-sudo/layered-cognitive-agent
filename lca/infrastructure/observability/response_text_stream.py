"""Incremental user-visible text extraction from streaming Decision JSON.

The LCA cognitive loop emits structured Decision JSON; only ``response_text``
(and plain prose fallbacks) may surface as OpenAI ``delta.content`` for LobeHub.

Architecture:
- ``StepTextDelta`` channel ``decision`` — raw LLM tokens (journal / replay)
- ``StepTextDelta`` channel ``answer`` — extracted user-visible deltas only
- ``DecisionMade.response_text`` — canonical final text when stream missed
"""

from __future__ import annotations

import re

_RESPONSE_KEY_RE = re.compile(r'"(?:response_text|response|text)"\s*:\s*"')
_ACTION_TYPE_MARKER = '"action_type"'
_JSON_PREFIXES = ("{", "```", "[")
_PROVIDER_TOOL_MARKUP_MARKERS = (
    "<call>",
    "<call_name>",
    "<call_args>",
    "</call>",
    "call_call",
    "redacted_thinking",
    "[tool call:",
    "[tool calls]",
)


def _decode_json_string_content(source: str, start: int) -> str:
    """Decode a JSON string value starting at ``start`` (after opening quote)."""
    parts: list[str] = []
    escaped = False
    for ch in source[start:]:
        if escaped:
            if ch == "n":
                parts.append("\n")
            elif ch == "t":
                parts.append("\t")
            elif ch == "r":
                parts.append("\r")
            else:
                parts.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            break
        parts.append(ch)
    return "".join(parts)


def extract_user_facing_answer(raw: str) -> str | None:
    """Extract user-visible text from a (possibly partial) Decision JSON blob."""
    text = raw.lstrip()
    if not text:
        return None

    if _ACTION_TYPE_MARKER not in text and not text.startswith(_JSON_PREFIXES):
        return text

    match = _RESPONSE_KEY_RE.search(text)
    if match is None:
        return None

    decoded = _decode_json_string_content(text, match.end())
    return decoded if decoded else None


class ResponseTextStreamExtractor:
    """Stateful extractor: raw LLM deltas in → user-visible answer deltas out."""

    def __init__(self) -> None:
        self._accumulated = ""
        self._decoded_visible = ""
        self._value_start: int | None = None
        self._plain_text = False

    @property
    def accumulated(self) -> str:
        return self._accumulated

    def reset(self) -> None:
        self._accumulated = ""
        self._decoded_visible = ""
        self._value_start = None
        self._plain_text = False

    def feed(self, delta: str) -> str:
        """Return newly decoded user-visible characters from ``delta``."""
        if not delta:
            return ""
        self._accumulated += delta
        if _is_provider_tool_markup(self._accumulated):
            if _RESPONSE_KEY_RE.search(self._accumulated):
                self._plain_text = False
                self._value_start = None
            else:
                return ""
        visible = self._visible_snapshot()
        if len(visible) <= len(self._decoded_visible):
            return ""
        new_part = visible[len(self._decoded_visible) :]
        self._decoded_visible = visible
        return new_part

    def _visible_snapshot(self) -> str:
        text = self._accumulated.lstrip()
        if not text:
            return ""

        if self._plain_text:
            if _is_provider_tool_markup(self._accumulated):
                return self._decoded_visible
            return self._accumulated

        if self._value_start is None and _looks_like_plain_prose(text):
            self._plain_text = True
            return self._accumulated

        if self._value_start is None:
            match = _RESPONSE_KEY_RE.search(text)
            if match is None:
                return ""
            self._value_start = match.end()

        value_start = self._value_start
        if value_start is None:
            return ""
        return _decode_json_string_content(text, value_start)


def _looks_like_plain_prose(text: str) -> bool:
    if _ACTION_TYPE_MARKER in text:
        return False
    if _is_provider_tool_markup(text):
        return False
    return not text.startswith(_JSON_PREFIXES)


def _is_provider_tool_markup(text: str) -> bool:
    lowered = text.lstrip().lower()
    return any(marker in lowered for marker in _PROVIDER_TOOL_MARKUP_MARKERS)
