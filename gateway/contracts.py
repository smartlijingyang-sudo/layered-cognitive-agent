"""Gateway HTTP 契约 —— UI catalog 生成器的只读数据源。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CreateRunRequest:
    question: str
    mode: str = "board"
    conversation_id: str | None = None
    """Ids returned by POST /conversations/{id}/attachments (Phase C)."""
    attachment_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CreateRunResponse:
    run_id: str
    trace_id: str


@dataclass(frozen=True)
class AttachmentUploadResponse:
    attachment_id: str
    name: str
    mime_type: str
    url: str
    size_bytes: int
