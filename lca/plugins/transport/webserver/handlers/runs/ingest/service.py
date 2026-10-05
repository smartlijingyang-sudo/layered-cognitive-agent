"""Mirror selected LobeHub file references through the governed ingest pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.infrastructure.attachment import FileStoreAttachmentIdentity
from lca.infrastructure.file.store import FileStore
from lca.plugins.transport.webserver.handlers.runs.api.file_reference_parsing import (
    collect_file_refs as _collect_file_refs,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.cache import (
    IngestCache,
    get_ingest_cache,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.fetcher import (
    FileFetcher,
    HttpxFileFetcher,
    content_hash,
    decode_data_uri,
    validate_file_integrity,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.models import (
    MAX_INGEST_FILE_BYTES,
    MAX_INGEST_FILES,
    FileIntegrityError,
    FileRef,
    IngestResult,
    IngestUrlPolicyError,
    LobeHubBridgeSettings,
    bridge_settings,
)
from lca.plugins.transport.webserver.handlers.runs.session.message.history import (
    extract_prior_turns,
)
from lca.plugins.transport.webserver.handlers.runs.session.message.text import (
    history_plain_text as _history_plain_text,
)
from lca.plugins.transport.webserver.handlers.runs.session.message.text import (
    visible_user_text as _visible_user_text,
)

_log = structlog.get_logger(__name__)
_LOCAL_FILE_URL_RE = re.compile(r"^/files/([a-z]+_[a-z0-9]+)$", re.IGNORECASE)


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


def parse_messages(
    messages: list[Any],
    *,
    assistant_home: Path | None = None,
    topic_id: str = "",
) -> ParsedMessages:
    """Parse text, current-turn file references, and compact prior-turn context."""
    if not messages:
        return ParsedMessages(user_text="")
    user_text = _extract_last_user_text(messages)
    last_user = _last_user_message(messages)
    file_refs = _collect_file_refs([last_user] if last_user is not None else [])
    prior_turns = extract_prior_turns(
        messages,
        plain_text_fn=_history_plain_text,
        assistant_home=assistant_home,
        topic_id=topic_id,
    )
    return ParsedMessages(
        user_text=user_text,
        file_refs=tuple(file_refs),
        prior_turns=prior_turns,
    )


def compose_run_question(
    user_text: str,
    attachment_ids: tuple[str, ...],
    store: FileStore,
) -> str:
    """Compose user text with this turn's FileStore-backed attachment context."""
    return FileStoreAttachmentIdentity(store).compose_question(user_text, attachment_ids)


async def prepare_run_from_messages(
    messages: list[Any],
    store: FileStore,
    *,
    fetcher: FileFetcher | None = None,
    assistant_home: Path | None = None,
    topic_id: str = "",
) -> LobeHubRunInput:
    """Parse, mirror current-turn files, and compose a final LCA run task."""
    parsed = parse_messages(messages, assistant_home=assistant_home, topic_id=topic_id)
    if not parsed.user_text:
        return LobeHubRunInput(user_text="", question="")
    ingest = await ingest_file_refs(
        parsed.file_refs, store, fetcher=fetcher, conversation_id=topic_id or None
    )
    question = compose_run_question(parsed.user_text, ingest.attachment_ids, store)
    return LobeHubRunInput(
        user_text=parsed.user_text,
        question=question,
        prior_turns=parsed.prior_turns,
        attachment_ids=ingest.attachment_ids,
        skipped_files=ingest.skipped,
    )


def select_ingest_files(refs: tuple[FileRef, ...]) -> tuple[FileRef, ...]:
    """Apply LobeHub-aligned size and count caps before any download is attempted."""
    selected: list[FileRef] = []
    for ref in refs:
        if not ref.url.strip():
            continue
        if ref.size_bytes is not None and ref.size_bytes > MAX_INGEST_FILE_BYTES:
            continue
        selected.append(ref)
        if len(selected) >= MAX_INGEST_FILES:
            break
    return tuple(selected)


async def ingest_file_refs(
    refs: tuple[FileRef, ...],
    store: FileStore,
    *,
    fetcher: FileFetcher | None = None,
    cache: IngestCache | None = None,
    settings: LobeHubBridgeSettings | None = None,
    conversation_id: str | None = None,
) -> IngestResult:
    """Mirror selected files through local, cache, and guarded remote paths."""
    cfg = settings if settings is not None else bridge_settings()
    active_fetcher = fetcher if fetcher is not None else HttpxFileFetcher(cfg)
    active_cache = cache if cache is not None else get_ingest_cache(store, cfg)
    attachment_ids: list[str] = []
    skipped: list[str] = []
    for ref in select_ingest_files(refs):
        local_id = try_resolve_local_file(ref, store)
        if local_id is not None:
            attachment_ids.append(local_id)
            _log.debug("file_resolved_locally", name=ref.name, attachment_id=local_id)
            continue
        cached_id = active_cache.resolve(ref)
        if cached_id is not None:
            attachment_ids.append(cached_id)
            continue
        try:
            data, mime = await load_bytes(ref, active_fetcher)
        except IngestUrlPolicyError as exc:
            _log.error(
                "lobehub_file_ingest_blocked",
                name=ref.name,
                url=ref.url,
                error=str(exc),
                hint="relative URLs must resolve to a local FileStore entry",
            )
            skipped.append(ref.name)
            continue
        except FileIntegrityError as exc:
            _log.warning(
                "lobehub_file_ingest_integrity",
                name=ref.name,
                url=ref.url,
                error=str(exc),
            )
            skipped.append(ref.name)
            continue
        except Exception as exc:
            _log.warning("lobehub_file_ingest_failed", name=ref.name, url=ref.url, error=str(exc))
            skipped.append(ref.name)
            continue
        if len(data) > MAX_INGEST_FILE_BYTES:
            skipped.append(ref.name)
            continue
        stored = store.put(
            data=data,
            name=ref.name,
            mime_type=mime or ref.mime_type,
            conversation_id=conversation_id,
        )
        active_cache.remember(
            ref,
            stored.attachment_id,
            size_bytes=len(data),
            content_hash=content_hash(data),
        )
        attachment_ids.append(stored.attachment_id)
    return IngestResult(attachment_ids=tuple(attachment_ids), skipped=tuple(skipped))


async def load_bytes(ref: FileRef, fetcher: FileFetcher) -> tuple[bytes, str]:
    """Load and integrity-check one data URI or policy-authorized remote file."""
    url = ref.url.strip()
    if url.startswith("data:"):
        data, mime = decode_data_uri(url)
        validate_file_integrity(data, ref.mime_type, mime, ref.name)
        return data, mime
    data, actual_mime = await fetcher.fetch(url)
    declared = ref.mime_type
    if declared and declared not in {"", "undefined", "plain/txt"}:
        validate_file_integrity(data, declared, actual_mime, ref.name)
        return data, declared
    validate_file_integrity(data, actual_mime, actual_mime, ref.name)
    return data, actual_mime


def try_resolve_local_file(ref: FileRef, store: FileStore | None) -> str | None:
    """Resolve local ``/files/{id}`` and LobeHub-ID references without HTTP."""
    if store is None:
        return None
    url = ref.url.strip()
    match = _LOCAL_FILE_URL_RE.match(url)
    if match is None:
        lobehub_id = ref.lobehub_id.strip()
        return lobehub_id if lobehub_id and store.exists(lobehub_id) else None
    attachment_id = match.group(1)
    return attachment_id if store.exists(attachment_id) else None


def _last_user_message(messages: list[Any]) -> dict[str, Any] | None:
    for item in reversed(messages):
        if isinstance(item, dict) and item.get("role") == "user":
            return item
    return None


def _extract_last_user_text(messages: list[Any]) -> str:
    for item in reversed(messages):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        text = _visible_user_text(item.get("content"))
        if text:
            return text
    return ""


__all__ = [
    "LobeHubRunInput",
    "ParsedMessages",
    "compose_run_question",
    "extract_prior_turns",
    "ingest_file_refs",
    "load_bytes",
    "parse_messages",
    "prepare_run_from_messages",
    "select_ingest_files",
    "try_resolve_local_file",
]
