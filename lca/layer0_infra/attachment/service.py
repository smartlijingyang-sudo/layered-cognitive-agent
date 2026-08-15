"""FileStore-backed AttachmentIdentity — prompt document + inbox staging."""

from __future__ import annotations

import re
from collections.abc import Sequence

from lca.contracts.models.core.attachment import AttachmentRecord
from lca.contracts.protocols.infra import AttachmentIdentity
from lca.layer0_infra.attachment.files_info import FilesInfoDocument
from lca.layer0_infra.attachment.layout import AttachmentLayout
from lca.layer0_infra.attachment.settings import AttachmentPolicyDocument, get_attachment_policy
from lca.layer0_infra.file_store import FileStore

_HTML_DOCTYPE = re.compile(rb"^\s*<!doctype\s+html", re.IGNORECASE)
_HTML_TAG = re.compile(rb"<html[\s>]", re.IGNORECASE)


def _looks_like_html(content: bytes) -> bool:
    """Heuristic: does the content look like an HTML document?"""
    head = content[:512]
    return bool(_HTML_DOCTYPE.search(head) or _HTML_TAG.search(head))


class FileStoreAttachmentIdentity(AttachmentIdentity):
    """Resolve store records, compose files_info, stage into run-scoped inbox."""

    def __init__(
        self,
        store: FileStore,
        *,
        policy: AttachmentPolicyDocument | None = None,
        layout: AttachmentLayout | None = None,
    ) -> None:
        self._store = store
        self._policy = policy if policy is not None else get_attachment_policy()
        self._layout = layout if layout is not None else AttachmentLayout(self._policy)

    def resolve(self, attachment_ids: Sequence[str]) -> tuple[AttachmentRecord, ...]:
        records: list[AttachmentRecord] = []
        seen: set[str] = set()
        for raw_id in attachment_ids:
            attachment_id = str(raw_id).strip()
            if not attachment_id or attachment_id in seen:
                continue
            stored = self._store.get(attachment_id)
            if stored is None:
                continue
            seen.add(attachment_id)
            records.append(
                AttachmentRecord(
                    attachment_id=stored.attachment_id,
                    name=stored.name,
                    mime_type=stored.mime_type,
                    size_bytes=stored.size_bytes,
                    url=stored.url,
                    content=self._inline_text(stored.attachment_id, stored.mime_type, stored.name),
                )
            )
        return tuple(records)

    def compose_question(self, user_text: str, attachment_ids: Sequence[str]) -> str:
        text = user_text.strip()
        document = FilesInfoDocument.from_records(self.resolve(attachment_ids), policy=self._policy)
        block = document.render()
        if not block:
            return text
        if not text:
            return block
        return f"{text}\n\n{block}"

    def stage_payload(self, run_id: str, attachment_ids: Sequence[str]) -> dict[str, bytes]:
        payload: dict[str, bytes] = {}
        for record in self.resolve(attachment_ids):
            raw = self._store.read_bytes(record.attachment_id)
            if raw is None:
                continue
            payload[self._layout.relative_file(run_id, record.name)] = raw
        return payload

    def listed_paths(
        self, root: str, run_id: str, attachment_ids: Sequence[str]
    ) -> tuple[str, ...]:
        paths: list[str] = []
        seen: set[str] = set()
        for record in self.resolve(attachment_ids):
            path = self._layout.absolute_file(root, run_id, record.name)
            if path in seen:
                continue
            seen.add(path)
            paths.append(path)
        return tuple(paths)

    def _inline_text(self, attachment_id: str, mime_type: str, name: str) -> str | None:
        if not self._policy.allows_inline(mime_type, name):
            return None
        raw = self._store.read_bytes(attachment_id)
        if raw is None or len(raw) > self._policy.inline_max_bytes:
            return None
        # Inline Gate: reject HTML content masquerading as other types.
        # This catches SPA fallback pages and expired-URL error pages.
        if not mime_type.startswith("text/html") and _looks_like_html(raw):
            return None
        return raw.decode("utf-8", errors="replace")
