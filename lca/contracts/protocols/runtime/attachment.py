"""Attachment / FileRef seams — ADR-0121.

Three independent Protocols, each owned by a separate Plugin:

  AttachmentResolver       — turns uploaded attachment_ids into FileRefs
  AttachmentStager         — copies FileRefs into machine inbox / sandbox guest
  AttachmentPromptRenderer — renders <files_info> / <uploaded_files> blocks

The actual sandbox-backend contract lives in
:mod:`lca.contracts.protocols.runtime.sandbox_backend`
(SandboxBackend) — that's what makes the sandbox fully replaceable
(Onlyboxes today, e2b / docker / ssh / in-memory test double tomorrow).

Every seam is debug-friendly: implementations must expose ``label`` so the
journal can attribute each side-effect, and each renderer block must round-trip
through a single ``render_*`` call so a future regression surfaces in one place.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.contracts.models.core.file_ref import FileRef
from lca.contracts.models.core.plane import PlaneRef
from lca.contracts.models.core.sandbox import MountEntry


@dataclass(frozen=True)
class ResolvedAttachment:
    """Pair returned by :meth:`AttachmentResolver.resolve` — keeps the
    underlying record around for inline-content / previews."""

    ref: FileRef
    inline_content: str | None = None


@runtime_checkable
class AttachmentResolver(Protocol):
    """Map ``attachment_id`` → :class:`FileRef`.

    Implementations must be pure (no I/O on resolve); the resolver that *does*
    need I/O is :class:`AttachmentStager`.
    """

    label: str

    def resolve(self, attachment_ids: Sequence[str]) -> tuple[ResolvedAttachment, ...]:
        """Return one :class:`ResolvedAttachment` per id, deduped, in input order."""
        ...

    def resolve_for_plane(self, ref: FileRef, plane: PlaneRef | None) -> FileRef:
        """Translate a generic :class:`FileRef` into the ``process_path`` for a
        concrete plane (``machine`` / ``sandbox`` / ``device``)."""
        ...


@runtime_checkable
class AttachmentStager(Protocol):
    """Copy bytes from FileStore onto a concrete plane.

    Implementations are expected to be idempotent: re-staging the same
    ``target_key`` is a no-op (sha256 dedup).
    """

    label: str

    def stage_to_machine(
        self,
        *,
        run_id: str,
        refs: Sequence[FileRef],
    ) -> dict[str, str]:
        """Stage onto the machine inbox; return ``{target_key: absolute_path}``."""
        ...

    def stage_to_sandbox(
        self,
        *,
        sandbox_id: str,
        refs: Sequence[FileRef],
    ) -> tuple[MountEntry, ...]:
        """Stage onto the named sandbox; return the mount manifest entries."""
        ...


@runtime_checkable
class AttachmentPromptRenderer(Protocol):
    """Render the three attachment-related prompt blocks.

    Every block is rendered by a single method so the system-role renderer can
    substitute all placeholders in one pass (no per-block drift).
    """

    label: str

    def identity_block(self, refs: Sequence[FileRef]) -> str:
        """Return ``<files_info>...</files_info>`` for LLM identity hints."""
        ...

    def guest_path_block(self, refs: Sequence[FileRef], plane: PlaneRef | None) -> str:
        """Return ``<uploaded_files>...</uploaded_files>`` with exact guest paths."""
        ...

    def inline_content_block(self, refs: Sequence[FileRef]) -> str:
        """Return ``<file id=...>content</file>`` for inline-text attachments."""
        ...


__all__ = [
    "AttachmentPromptRenderer",
    "AttachmentResolver",
    "AttachmentStager",
    "ResolvedAttachment",
]
