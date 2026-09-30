"""Group pages for one assistant home.

The directory and index name come from the context layout. Writing goes
through :class:`PageDirectory`, the same record people use.
"""

from __future__ import annotations

from lca.infrastructure.memory.contextfiles.domain.layout import ContextLayout, packaged_layout
from lca.infrastructure.memory.contextfiles.domain.people import NamedPage
from lca.infrastructure.memory.contextfiles.events.publisher import GroupRecorded
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore
from lca.infrastructure.memory.contextfiles.service.pages import PageDirectory

_HEADING = "群体"


class GroupsDirectory:
    """Group pages for one assistant home."""

    def __init__(
        self,
        store: FileStore,
        publisher: DomainEventPublisher | None = None,
        *,
        layout: ContextLayout | None = None,
    ) -> None:
        chosen = packaged_layout() if layout is None else layout
        self._pages = PageDirectory(
            store,
            directory=chosen.groups_dir,
            index_name=chosen.groups_index,
            heading=_HEADING,
            publisher=publisher,
            event_for=GroupRecorded,
        )

    def upsert(self, name: str, body: str, *, slug: str | None = None) -> NamedPage:
        """Create or replace one group page, then rewrite the index."""

        return self._pages.upsert(name, body, slug=slug)

    def list(self) -> tuple[NamedPage, ...]:
        """Return group pages. The index file is not a group."""

        return self._pages.list()


__all__ = ["GroupsDirectory"]
