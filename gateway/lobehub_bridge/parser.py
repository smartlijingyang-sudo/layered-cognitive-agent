"""Parse LobeHub OpenAI-style messages into LCA run input parts.

LobeHub injects uploaded files as XML inside user content (``<files>`` /
``<file url=...>``) and as ``image_url`` multimodal parts. This module
extracts those references without depending on LobeHub server APIs.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlparse

from gateway.lobehub_bridge.constants import (
    AGENT_MGMT_BEGIN,
    AGENT_MGMT_END,
    AVAILABLE_TOOLS_BEGIN,
    AVAILABLE_TOOLS_END,
    FEEDBACK_ANALYSIS_BEGIN,
    FEEDBACK_ANALYSIS_END,
    SYSTEM_CONTEXT_BEGIN,
    SYSTEM_CONTEXT_END,
)
from gateway.lobehub_bridge.conversation import extract_prior_turns
from gateway.lobehub_bridge.models import FileRef, ParsedMessages

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
_FILE_TAG_RE = re.compile(
    r"<file\s+([^>]*?)(?:/>|>\s*.*?\s*</file>)",
    re.IGNORECASE | re.DOTALL,
)
_IMAGE_TAG_RE = re.compile(
    r"<image\s+([^>]*?)(?:/>|>\s*.*?\s*</image>)",
    re.IGNORECASE | re.DOTALL,
)
_DATA_URI_RE = re.compile(r"^data:([^;,]+)?;base64,", re.IGNORECASE)


def parse_messages(messages: list[Any]) -> ParsedMessages:
    """Extract user text, file refs, and compact history from OpenAI messages."""
    if not messages:
        return ParsedMessages(user_text="")

    user_text = _extract_last_user_text(messages)
    file_refs = _collect_file_refs(messages)
    prior_turns = extract_prior_turns(messages, plain_text_fn=_message_plain_text)
    return ParsedMessages(
        user_text=user_text,
        file_refs=tuple(file_refs),
        prior_turns=prior_turns,
    )


def _extract_last_user_text(messages: list[Any]) -> str:
    for item in reversed(messages):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        text = _visible_user_text(item.get("content"))
        if text:
            return text
    return ""


def _visible_user_text(content: Any) -> str:
    if isinstance(content, str):
        return _strip_system_context(content)
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                text = _strip_system_context(str(part.get("text", "")))
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _strip_system_context(text: str) -> str:
    begin = text.find(SYSTEM_CONTEXT_BEGIN)
    if begin >= 0:
        text = text[:begin]
    end = text.find(SYSTEM_CONTEXT_END)
    if end >= 0:
        text = text[:end]
    text = _strip_lobehub_runtime_xml(text)
    return _unwrap_lobehub_eval_envelope(text).strip()


_EVAL_MESSAGE_RE = re.compile(
    r'(?is)message\s*=\s*"((?:[^"\\]|\\.)*)"',
)


def _unwrap_lobehub_eval_envelope(text: str) -> str:
    """Extract real user message from AgentSignal / satisfaction-judge wrappers.

    Example pollution seen in journal::

        Judge the user's overall satisfaction.
        message="分析这个自查表的内容"
        serializedContext=""
    """
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
    # Unescape common JSON-ish sequences without treating unicode as escapes.
    return (
        inner.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
        .strip()
        or stripped
    )


def _strip_lobehub_runtime_xml(text: str) -> str:
    """Remove LobeHub-injected tool/agent XML blocks from user-visible text."""
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


def _collect_file_refs(messages: list[Any]) -> list[FileRef]:
    seen_urls: set[str] = set()
    refs: list[FileRef] = []

    def add(ref: FileRef) -> None:
        url = ref.url.strip()
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        refs.append(ref)

    for item in messages:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        blobs = _content_blobs(content)
        for blob in blobs:
            for match in _FILE_TAG_RE.finditer(blob):
                add(_file_ref_from_attrs(match.group(1), source="file_tag"))
            for match in _IMAGE_TAG_RE.finditer(blob):
                add(
                    _file_ref_from_attrs(
                        match.group(1), source="image_tag", default_mime="image/png"
                    )
                )
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "image_url":
                    continue
                image_url = part.get("image_url")
                url = ""
                if isinstance(image_url, dict):
                    url = str(image_url.get("url", "")).strip()
                elif isinstance(image_url, str):
                    url = image_url.strip()
                if not url:
                    continue
                add(
                    FileRef(
                        name=_name_from_url(url),
                        url=url,
                        mime_type=_mime_from_data_uri(url) or "image/png",
                        source="image_url",
                    )
                )
    return refs


def _content_blobs(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        out: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                out.append(str(part.get("text", "")))
        return out
    return []


def _parse_attrs(raw: str) -> dict[str, str]:
    return {key: unquote(value) for key, value in _ATTR_RE.findall(raw)}


def _file_ref_from_attrs(
    raw_attrs: str,
    *,
    source: str,
    default_mime: str = "application/octet-stream",
) -> FileRef:
    attrs = _parse_attrs(raw_attrs)
    name = (
        attrs.get("name") or attrs.get("filename") or _name_from_url(attrs.get("url", ""))
    ).strip()
    url = attrs.get("url", "").strip()
    mime = (attrs.get("type") or attrs.get("fileType") or default_mime).strip() or default_mime
    size_raw = attrs.get("size", "").strip()
    size = int(size_raw) if size_raw.isdigit() else None
    if attrs.get("error"):
        return FileRef(
            name=name or "file",
            url="",
            mime_type=mime,
            lobehub_id=attrs.get("id", ""),
            source=source,
        )
    return FileRef(
        name=name or "file",
        url=url,
        mime_type=mime,
        lobehub_id=attrs.get("id", ""),
        size_bytes=size,
        source=source,
    )


def _name_from_url(url: str) -> str:
    if url.startswith("data:"):
        mime = _mime_from_data_uri(url) or "application/octet-stream"
        ext = mime.split("/")[-1] if "/" in mime else "bin"
        return f"upload.{ext}"
    path = urlparse(url).path
    base = path.rsplit("/", 1)[-1] if path else "file"
    return unquote(base) or "file"


def _mime_from_data_uri(url: str) -> str | None:
    match = _DATA_URI_RE.match(url)
    if not match:
        return None
    return (match.group(1) or "application/octet-stream").strip()


def _message_plain_text(content: Any) -> str:
    if isinstance(content, str):
        return _strip_lobehub_runtime_xml(_strip_system_context(content))
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = _strip_lobehub_runtime_xml(_strip_system_context(str(part.get("text", ""))))
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def extract_user_question(messages: list[Any]) -> str:
    """Extract last user message text from OpenAI-style messages."""
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
