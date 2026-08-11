"""Typed contracts for LobeHub → LCA run input bridging."""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.models.core.conversation import ConversationTurn


@dataclass(frozen=True)
class FileRef:
    """A user-uploaded asset referenced in OpenAI-style messages."""

    name: str
    url: str
    mime_type: str = "application/octet-stream"
    lobehub_id: str = ""
    size_bytes: int | None = None
    source: str = "file_tag"


@dataclass(frozen=True)
class ParsedMessages:
    """Structured view of a LobeHub chat/completions payload."""

    user_text: str
    file_refs: tuple[FileRef, ...] = ()
    prior_turns: tuple[ConversationTurn, ...] = ()


@dataclass(frozen=True)
class IngestResult:
    """Outcome of mirroring remote LobeHub files into LCA FileStore."""

    attachment_ids: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()


@dataclass(frozen=True)
class LobeHubRunInput:
    """Final input for ``create_run_session`` from an OpenAI messages array."""

    user_text: str
    question: str
    prior_turns: tuple[ConversationTurn, ...] = ()
    attachment_ids: tuple[str, ...] = ()
    skipped_files: tuple[str, ...] = field(default_factory=tuple)
