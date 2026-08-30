"""Turn an OpenAI/LobeHub messages payload into a ready-to-run LCA input.

Text normalization, history selection, and file-reference parsing are owned by
focused modules.  This facade keeps the ingress order explicit: parse the
current turn, mirror only its files, then compose the final prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gateway.runs.file_reference_parsing import collect_file_refs as _collect_file_refs
from gateway.runs.ingest import FileFetcher, FileRef, ingest_file_refs
from gateway.runs.message_history import (
    extract_prior_turns,
)
from gateway.runs.message_text import history_plain_text as _history_plain_text
from gateway.runs.message_text import visible_user_text as _visible_user_text
from lca.contracts.models.core.conversation import ConversationTurn
from lca.layer0_infra.attachment import FileStoreAttachmentIdentity
from lca.layer0_infra.file_store import FileStore


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


def parse_messages(messages: list[Any]) -> ParsedMessages:
    """Parse text, current-turn file references, and compact prior-turn context."""
    if not messages:
        return ParsedMessages(user_text="")
    user_text = _extract_last_user_text(messages)
    last_user = _last_user_message(messages)
    file_refs = _collect_file_refs([last_user] if last_user is not None else [])
    prior_turns = extract_prior_turns(messages, plain_text_fn=_history_plain_text)
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
) -> LobeHubRunInput:
    """Parse, mirror current-turn files, and compose a final LCA run task."""
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


def _last_user_message(messages: list[Any]) -> dict[str, Any] | None:
    """Return the final user-role payload, if the request includes one."""
    for item in reversed(messages):
        if isinstance(item, dict) and item.get("role") == "user":
            return item
    return None


def _extract_last_user_text(messages: list[Any]) -> str:
    """Extract the last non-empty user-visible text value from a request."""
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
    "parse_messages",
    "prepare_run_from_messages",
]
