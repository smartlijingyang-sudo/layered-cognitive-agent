"""Attachment identity — this-turn file records. No I/O."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AttachmentRecord:
    """One user-visible file bound to the current turn."""

    attachment_id: str
    name: str
    mime_type: str
    size_bytes: int
    url: str
    content: str | None = None
