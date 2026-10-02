"""Side-chat branch memory for one assistant home.

A side chat owns ``side-chats/<id>/MEMORY.md``. Branch-specific durable
facts write there and never touch the main curated projection. Retrieval
reads both the main structured memory and the branch file through the same
``FileStore`` port.
"""

from __future__ import annotations

import logging

from lca.contracts.mechanisms.content.addressable import sha256_hex
from lca.infrastructure.memory.contextfiles.domain.curated import contains_secret
from lca.infrastructure.memory.contextfiles.domain.edit import (
    FileVersion,
    require_fresh,
)
from lca.infrastructure.memory.contextfiles.domain.layout import ContextLayout, packaged_layout
from lca.infrastructure.memory.contextfiles.domain.search import best_documents
from lca.infrastructure.memory.contextfiles.domain.sidechat import (
    SideChatRecord,
    chat_slug,
    parse_side_chat_memory,
    render_side_chat_memory,
)
from lca.infrastructure.memory.contextfiles.events.publisher import SideChatRecorded
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.ports.file_store import (
    FileSnapshot,
    FileStore,
)

logger = logging.getLogger(__name__)


class SideChatDirectory:
    """Branch memory files under ``side-chats/`` of an assistant home."""

    def __init__(
        self,
        store: FileStore,
        publisher: DomainEventPublisher | None = None,
        *,
        layout: ContextLayout | None = None,
    ) -> None:
        self._store = store
        self._publisher = publisher
        self._layout = packaged_layout() if layout is None else layout

    def write(
        self,
        chat_id: str,
        content: str,
        *,
        source: str = "user",
        trigger: str = "side chat",
        recorded_on: str = "",
    ) -> SideChatRecord:
        """Append one branch fact to ``side-chats/<id>/MEMORY.md``.

        The write is guarded against concurrent modification: the file is
        snapshotted before reading and again before replacing, so a stale
        read cannot clobber a concurrent edit. An identical content line is
        idempotent and returns the existing record.
        """

        if contains_secret(content):
            raise ValueError("credential_rejected")
        slug = chat_slug(chat_id)
        relative = self._layout.side_chat_memory_path(slug)
        before = self._store.snapshot(relative)
        current = self._read(relative)
        existing = parse_side_chat_memory(current)
        new_id = _record_id(content)
        for record in existing:
            if record.record_id == new_id:
                return record
        record = SideChatRecord(
            record_id=new_id,
            content=content.strip(),
            source=source,
            trigger=trigger,
            recorded_on=recorded_on,
        )
        rendered = render_side_chat_memory((*tuple(existing), record))
        after = self._store.snapshot(relative)
        require_fresh(_version(before), _version(after))
        self._store.atomic_replace(relative, rendered)
        logger.info("side chat wrote chat=%s path=%s", slug, relative)
        if self._publisher is not None:
            self._publisher.publish(
                SideChatRecorded(chat_id=slug, record_id=record.record_id, path=relative)
            )
        return record

    def read(self, chat_id: str) -> str:
        """Return the branch memory Markdown for one side chat."""

        return self._read(self._layout.side_chat_memory_path(chat_slug(chat_id)))

    def records(self, chat_id: str) -> tuple[SideChatRecord, ...]:
        """Return parsed branch memory records for one side chat."""

        return parse_side_chat_memory(self.read(chat_id))

    def search(self, query: str, chat_id: str, *, limit: int = 5) -> list[SideChatRecord]:
        """Search one branch's memory and return matching records."""

        records = self.records(chat_id)
        matched = best_documents(
            [
                (record.record_id, record.content, self._layout.side_chat_memory_path(chat_id))
                for record in records
            ],
            query,
            limit=limit,
        )
        by_id = {record.record_id: record for record in records}
        return [by_id[doc_id] for doc_id, _content, _path in matched if doc_id in by_id]

    def list_chats(self) -> tuple[str, ...]:
        """Return side-chat ids that have a branch memory file."""

        return tuple(self._store.list_dir(self._layout.side_chats_dir))

    def _read(self, relative: str) -> str:
        try:
            return self._store.read_text(relative)
        except OSError:
            return ""


def _record_id(content: str) -> str:
    digest = sha256_hex(content.encode("utf-8"), length=16)
    return f"sc-{digest}"


def _version(snapshot: FileSnapshot | None) -> FileVersion | None:
    if snapshot is None:
        return None
    return FileVersion(path=str(snapshot.path), mtime_ns=int(snapshot.mtime_ns))


__all__ = ["SideChatDirectory"]
