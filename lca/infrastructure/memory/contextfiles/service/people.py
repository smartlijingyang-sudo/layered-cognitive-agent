"""Person pages for one assistant home.

The directory and index name come from the context layout. Writing goes
through :class:`PageDirectory`, the same record groups use.
"""

from __future__ import annotations

from lca.infrastructure.memory.contextfiles.domain.layout import ContextLayout, packaged_layout
from lca.infrastructure.memory.contextfiles.domain.people import NamedPage
from lca.infrastructure.memory.contextfiles.events.publisher import PersonRecorded
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore
from lca.infrastructure.memory.contextfiles.service.pages import PageDirectory

_HEADING = "人物"


class PeopleDirectory:
    """Person pages for one assistant home."""

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
            directory=chosen.people_dir,
            index_name=chosen.people_index,
            heading=_HEADING,
            publisher=publisher,
            event_for=PersonRecorded,
        )

    def upsert(self, name: str, body: str, *, slug: str | None = None) -> NamedPage:
        """Create or replace one person page, then rewrite the index."""

        return self._pages.upsert(name, body, slug=slug)

    def set_intimacy(self, slug: str, score: float) -> NamedPage | None:
        """Update one person's intimacy score and rewrite the index."""

        return self._pages.set_intimacy(slug, score)

    def list(self) -> tuple[NamedPage, ...]:
        """Return person pages. The index file is not a person."""

        return self._pages.list()


__all__ = ["PeopleDirectory"]
