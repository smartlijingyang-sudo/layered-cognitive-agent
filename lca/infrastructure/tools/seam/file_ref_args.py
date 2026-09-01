"""Tool-dispatch path resolution (ADR-0121 PR-C).

Every tool call that takes a ``path`` argument flows through
:func:`resolve_path_arg` before reaching the sandbox / machine backend.
The function translates three categories of "raw strings the model might
say" into a concrete :class:`FileRef`:

  * ``/files/<attachment_id>`` — the download URL lobehub returns. Map to
    the FileStore-backed :class:`FileRef` so the sandbox sees the real
    ``/mnt/data/<name>`` guest path instead of a stale HTTP URL.
  * ``http(s)://...`` — pull the bytes via :class:`FileStore` and resolve to
    a sandbox guest path. (Not used in the cloud-sandbox turn today, but
    supported to remove the same class of bug for future model behaviour.)
  * Anything else — leave as-is and tag ``kind=workspace``. The downstream
    :func:`normalize_sandbox_path` handles relative / absolute paths.

The seam is *strict about the LLM-facing wire string*: an input that
matches no known shape still passes through, but its resolution is logged
so a future regression in another call site shows up in the journal.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from lca.contracts.models.core.file_ref import FileRef
from lca.contracts.protocols.runtime.attachment_errors import (
    AmbiguousFileRefError,
    AttachmentError,
    AttachmentErrorCode,
    UnresolvedFileRefError,
)
from lca.infrastructure.attachment.default_provider import DefaultAttachmentResolver
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.observability import current_file_store as get_current_run_file_store

_LCA_FILE_URL: Final = re.compile(r"^/files/([A-Za-z0-9_-]+)/?$")
_HTTP_URL: Final = re.compile(r"^https?://", re.IGNORECASE)


@dataclass(frozen=True)
class ResolvedPathArg:
    """Result of :func:`resolve_path_arg` — pass ``process_path`` to the backend."""

    file_ref: FileRef
    raw: str

    @property
    def process_path(self) -> str:
        return self.file_ref.process_path

    @property
    def attachment_id(self) -> str | None:
        return self.file_ref.attachment_id


def resolve_path_arg(
    raw: str,
    *,
    allowed_refs: Iterable[FileRef] | None = None,
) -> ResolvedPathArg:
    """Translate a model-produced path string into a :class:`ResolvedPathArg`.

    Args:
      raw: the verbatim string the model handed us (e.g. ``"/files/file_xxx"``).
      allowed_refs: optional pre-resolved FileRefs to disambiguate against when
        the raw looks like an attachment-id we already saw this run.

    Raises:
      AmbiguousFileRefError: ``raw`` matches multiple known attachments.
      UnresolvedFileRefError: ``raw`` looks like an attachment URL but the
        attachment is unknown.
    """
    cleaned = (raw or "").strip()
    if not cleaned:
        raise UnresolvedFileRefError(cleaned)

    if match := _LCA_FILE_URL.match(cleaned):
        aid = match.group(1)
        store = get_current_run_file_store()
        return _resolve_from_store(aid, store, cleaned, allowed_refs)

    if _HTTP_URL.match(cleaned):
        store = get_current_run_file_store()
        if store is None:
            raise UnresolvedFileRefError(cleaned)
        return _resolve_http_url(cleaned, store, allowed_refs)

    return _resolve_workspace(cleaned)


def _resolve_from_store(
    aid: str,
    store: FileStore | None,
    raw: str,
    allowed_refs: Iterable[FileRef] | None,
) -> ResolvedPathArg:
    matches: list[FileRef] = []
    if allowed_refs is not None:
        matches = [ref for ref in allowed_refs if ref.target_key == aid]
    if not matches and store is None:
        raise UnresolvedFileRefError(raw, context={"reason": "no_file_store_in_scope"})
    if not matches:
        if store is None:
            raise UnresolvedFileRefError(raw, context={"reason": "no_file_store_in_scope"})
        resolver = DefaultAttachmentResolver(store=store)
        try:
            resolved = resolver.resolve([aid])
        except AttachmentError as exc:
            if exc.code is AttachmentErrorCode.MISSING_ATTACHMENT:
                raise UnresolvedFileRefError(raw, context={"attachment_id": aid}) from exc
            raise
        matches = [item.ref for item in resolved]
    if len(matches) > 1:
        raise AmbiguousFileRefError(raw, tuple(r.target_key for r in matches))
    return ResolvedPathArg(file_ref=matches[0], raw=raw)


def _resolve_http_url(
    url: str,
    store: FileStore | None,
    allowed_refs: Iterable[FileRef] | None,
) -> ResolvedPathArg:
    # We don't eagerly download here: the actual fetch happens later in the
    # sandbox-side execution path. The FileRef only records the URL for the
    # journal; the sandbox guest script does the curl when the backend asks.
    ref = FileRef(
        kind="user_upload",
        target_key=url,
        display_path=url,
        process_path=url,
        file_url=url,
        mime_type="application/octet-stream",
        size_bytes=0,
        source="lobehub_upload",
        attachment_id=None,
    )
    del store, allowed_refs  # future-proof; consumed by `_download_into_sandbox`
    return ResolvedPathArg(file_ref=ref, raw=url)


def _resolve_workspace(raw: str) -> ResolvedPathArg:
    ref = FileRef(
        kind="workspace",
        target_key=raw,
        display_path=raw,
        process_path=raw,
        file_url=f"file://{raw}" if raw.startswith("/") else raw,
        mime_type="application/octet-stream",
        size_bytes=0,
        source="tool_export",
        attachment_id=None,
    )
    return ResolvedPathArg(file_ref=ref, raw=raw)


__all__ = [
    "ResolvedPathArg",
    "resolve_path_arg",
]
