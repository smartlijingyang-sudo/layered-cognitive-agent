"""LobeHub messages[] → RunInput. Parse, history, compose question."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlparse

from gateway.runs.ingest import FileFetcher, FileRef, ingest_file_refs
from lca.contracts.models.core.conversation import ConversationTurn
from lca.layer0_infra.attachment import FileStoreAttachmentIdentity, get_attachment_policy
from lca.layer0_infra.file_store import FileStore

# Conversation history injected before the latest user turn.
MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 6000

# LobeHub agent runtime injects tool/agent XML into user turns — strip for LCA prompt.
AVAILABLE_TOOLS_BEGIN = "<available_tools"
AVAILABLE_TOOLS_END = "</available_tools>"
AGENT_MGMT_BEGIN = "<agent_management_context>"
AGENT_MGMT_END = "</agent_management_context>"

# Agent Signal feedback-analysis envelope (must not enter LCA user task / history).
FEEDBACK_ANALYSIS_BEGIN = "<feedback_analysis_context>"
FEEDBACK_ANALYSIS_END = "</feedback_analysis_context>"


@dataclass(frozen=True)
class ParsedMessages:
    """Structured view of a LobeHub chat/completions payload."""

    user_text: str
    file_refs: tuple[FileRef, ...] = ()
    prior_turns: tuple[ConversationTurn, ...] = ()


@dataclass(frozen=True)
class LobeHubRunInput:
    """Final input for ``create_run_session`` from an OpenAI messages array."""

    user_text: str
    question: str
    prior_turns: tuple[ConversationTurn, ...] = ()
    attachment_ids: tuple[str, ...] = ()
    skipped_files: tuple[str, ...] = field(default_factory=tuple)


def extract_prior_turns(messages: list[Any], *, plain_text_fn: Any) -> tuple[ConversationTurn, ...]:
    """Prior user/assistant turns before the last user message (native messages[] slice)."""
    turns: list[ConversationTurn] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = plain_text_fn(item.get("content"))
        if not text:
            continue
        turns.append(ConversationTurn(role=role, content=text))

    if len(turns) <= 1:
        return ()

    if turns and turns[-1].role == "user":
        turns = turns[:-1]

    if not turns:
        return ()

    selected = turns[-MAX_HISTORY_MESSAGES:]
    return tuple(_truncate_turns_to_budget(selected, MAX_HISTORY_CHARS))


def _truncate_turns_to_budget(
    turns: list[ConversationTurn], max_chars: int
) -> list[ConversationTurn]:
    """Keep the most recent turns within a total character budget."""
    if max_chars <= 0:
        return []
    kept: list[ConversationTurn] = []
    used = 0
    for turn in reversed(turns):
        content = turn.content
        if len(content) > max_chars:
            content = "…" + content[-max_chars:]
        need = len(content) + (2 if kept else 0)
        if used + need > max_chars and kept:
            break
        kept.append(ConversationTurn(role=turn.role, content=content))
        used += need
    kept.reverse()
    return kept


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
    prior_turns = extract_prior_turns(messages, plain_text_fn=_history_plain_text)
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
    policy = get_attachment_policy()
    begin = text.find(policy.system_context_open)
    if begin < 0:
        begin = text.find(policy.system_context_open_prefix)
    if begin >= 0:
        text = text[:begin]
    end = text.find(policy.system_context_close)
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
        for ref in _structured_file_refs(item):
            add(ref)
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


def _structured_file_refs(item: dict[str, Any]) -> list[FileRef]:
    """First-class files on the Run wire. Not scraped from prompt HTML."""
    refs: list[FileRef] = []
    raw_files = item.get("files")
    if raw_files is None:
        raw_files = item.get("fileList")
    if isinstance(raw_files, list):
        for part in raw_files:
            ref = _file_ref_from_mapping(part, source="files")
            if ref is not None:
                refs.append(ref)
    raw_images = item.get("imageList")
    if isinstance(raw_images, list):
        for part in raw_images:
            if not isinstance(part, dict):
                continue
            url = str(part.get("url", "")).strip()
            if not url:
                continue
            name = str(part.get("alt") or part.get("name") or part.get("id") or "").strip()
            refs.append(
                FileRef(
                    name=name or _name_from_url(url),
                    url=url,
                    mime_type=str(part.get("mime_type") or part.get("fileType") or "image/png"),
                    lobehub_id=str(part.get("id", "")),
                    source="imageList",
                )
            )
    return refs


def _file_ref_from_mapping(part: Any, *, source: str) -> FileRef | None:
    if not isinstance(part, dict):
        return None
    url = str(part.get("url", "")).strip()
    if not url or part.get("inaccessible"):
        return None
    name = str(part.get("name") or part.get("filename") or _name_from_url(url)).strip()
    mime = str(
        part.get("mime_type")
        or part.get("fileType")
        or part.get("type")
        or "application/octet-stream"
    ).strip()
    size_raw = part.get("size")
    if size_raw is None:
        size_raw = part.get("size_bytes")
    size_ok = isinstance(size_raw, int) or (isinstance(size_raw, str) and size_raw.isdigit())
    size = int(size_raw) if size_ok else None
    return FileRef(
        name=name or "file",
        url=url,
        mime_type=mime or "application/octet-stream",
        lobehub_id=str(part.get("id", "")),
        size_bytes=size,
        source=source,
    )


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


def _history_plain_text(content: Any) -> str:
    """Keep LobeHub <files_info> in prior turns; drop runtime tool/agent XML only."""
    if isinstance(content, str):
        return _strip_lobehub_runtime_xml(_unwrap_lobehub_eval_envelope(content)).strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = _strip_lobehub_runtime_xml(
                    _unwrap_lobehub_eval_envelope(str(part.get("text", "")))
                ).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def compose_run_question(
    user_text: str,
    attachment_ids: tuple[str, ...],
    store: FileStore,
) -> str:
    """User text plus this-turn <files_info> (LobeHub message identity)."""
    return FileStoreAttachmentIdentity(store).compose_question(user_text, attachment_ids)


async def prepare_run_from_messages(
    messages: list[Any],
    store: FileStore,
    *,
    fetcher: FileFetcher | None = None,
) -> LobeHubRunInput:
    """Parse, ingest attachments, and compose the LCA run task (last user turn only)."""
    parsed = parse_messages(messages)
    if not parsed.user_text:
        return LobeHubRunInput(user_text="", question="")

    ingest = await ingest_file_refs(parsed.file_refs, store, fetcher=fetcher)
    question = compose_run_question(parsed.user_text, ingest.attachment_ids, store)
    return LobeHubRunInput(
        user_text=parsed.user_text,
        question=question,
        prior_turns=parsed.prior_turns,
        attachment_ids=ingest.attachment_ids,
        skipped_files=ingest.skipped,
    )
