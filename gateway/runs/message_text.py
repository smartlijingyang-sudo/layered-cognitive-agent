"""Normalize user-visible and historical text from LobeHub message content."""

from __future__ import annotations

import re
from typing import Any

from lca.layer0_infra.attachment import get_attachment_policy

AVAILABLE_TOOLS_BEGIN = "<available_tools"
AVAILABLE_TOOLS_END = "</available_tools>"
AGENT_MGMT_BEGIN = "<agent_management_context>"
AGENT_MGMT_END = "</agent_management_context>"
FEEDBACK_ANALYSIS_BEGIN = "<feedback_analysis_context>"
FEEDBACK_ANALYSIS_END = "</feedback_analysis_context>"

_EVAL_MESSAGE_RE = re.compile(r'(?is)message\s*=\s*"((?:[^"\\]|\\.)*)"')


def visible_user_text(content: Any) -> str:
    """Extract only user-visible text from a current OpenAI message content value."""
    if isinstance(content, str):
        return strip_system_context(content)
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "text":
                continue
            text = strip_system_context(str(part.get("text", "")))
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return ""


def strip_system_context(text: str) -> str:
    """Remove attachment, runtime, and evaluation wrappers from current user text."""
    policy = get_attachment_policy()
    begin = text.find(policy.system_context_open)
    if begin < 0:
        begin = text.find(policy.system_context_open_prefix)
    if begin >= 0:
        text = text[:begin]
    end = text.find(policy.system_context_close)
    if end >= 0:
        text = text[:end]
    return unwrap_lobehub_eval_envelope(strip_lobehub_runtime_xml(text)).strip()


def unwrap_lobehub_eval_envelope(text: str) -> str:
    """Extract the original user message from an Agent Signal evaluation wrapper."""
    stripped = text.strip()
    if not stripped:
        return stripped
    lower = stripped.lower()
    if "serializedcontext" not in lower and "overall satisfaction" not in lower:
        return stripped
    match = _EVAL_MESSAGE_RE.search(stripped)
    if not match:
        return stripped
    inner = match.group(1)
    return (
        inner.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
        .strip()
        or stripped
    )


def strip_lobehub_runtime_xml(text: str) -> str:
    """Remove LobeHub-injected tool, agent, and feedback XML blocks."""
    for open_tag, close_tag in (
        (AVAILABLE_TOOLS_BEGIN, AVAILABLE_TOOLS_END),
        (AGENT_MGMT_BEGIN, AGENT_MGMT_END),
        (FEEDBACK_ANALYSIS_BEGIN, FEEDBACK_ANALYSIS_END),
    ):
        while True:
            start = text.find(open_tag)
            if start < 0:
                break
            end = text.find(close_tag, start)
            if end < 0:
                text = text[:start]
                break
            text = text[:start] + text[end + len(close_tag) :]
    return text


def message_plain_text(content: Any) -> str:
    """Return text with current-message attachment context and runtime XML removed."""
    if isinstance(content, str):
        return strip_lobehub_runtime_xml(strip_system_context(content))
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = strip_lobehub_runtime_xml(strip_system_context(str(part.get("text", ""))))
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def history_plain_text(content: Any) -> str:
    """Keep prior-turn file context while excluding runtime and evaluation wrappers."""
    if isinstance(content, str):
        return strip_lobehub_runtime_xml(unwrap_lobehub_eval_envelope(content)).strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = strip_lobehub_runtime_xml(
                    unwrap_lobehub_eval_envelope(str(part.get("text", "")))
                ).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


__all__ = [
    "AGENT_MGMT_BEGIN",
    "AGENT_MGMT_END",
    "AVAILABLE_TOOLS_BEGIN",
    "AVAILABLE_TOOLS_END",
    "FEEDBACK_ANALYSIS_BEGIN",
    "FEEDBACK_ANALYSIS_END",
    "history_plain_text",
    "message_plain_text",
    "strip_lobehub_runtime_xml",
    "strip_system_context",
    "unwrap_lobehub_eval_envelope",
    "visible_user_text",
]
