"""Write one person page and refresh the index from those pages.

The directory and index name come from the context layout. The page is the
record. A failed index write leaves the page that just landed.
"""

from __future__ import annotations

import logging

from lca.infrastructure.memory.contextfiles.domain.layout import ContextLayout, packaged_layout
from lca.infrastructure.memory.contextfiles.domain.people import (
    PersonPage,
    parse_person_page,
    render_people_index,
    render_person_page,
    slug_for,
)
from lca.infrastructure.memory.contextfiles.events.publisher import PersonRecorded
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore

logger = logging.getLogger(__name__)


class PeopleDirectory:
    """Person pages for one assistant home."""

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

    def upsert(self, name: str, body: str, *, slug: str | None = None) -> PersonPage:
        """Create or replace one person page, then rewrite the index."""

        page = PersonPage(slug=slug_for(slug or name), name=name.strip(), body=body.strip())
        if not page.name or not page.body:
            raise ValueError("person name and body are required")
        self._store.atomic_replace(
            self._layout.person_page_path(page.slug), render_person_page(page)
        )
        pages = self.list()
        self._store.atomic_replace(self._layout.people_index_path, render_people_index(pages))
        logger.info("person page wrote slug=%s path=%s", page.slug, self._layout.people_dir)
        if self._publisher is not None:
            self._publisher.publish(PersonRecorded(slug=page.slug, name=page.name))
        return page

    def list(self) -> tuple[PersonPage, ...]:
        """Return person pages. The index file is not a person."""

        pages: list[PersonPage] = []
        index_name = self._layout.people_index
        for name in self._store.list_dir(self._layout.people_dir):
            if name == index_name or not name.endswith(".md"):
                continue
            slug = name[: -len(".md")]
            try:
                text = self._store.read_text(self._layout.person_page_path(slug))
            except OSError:
                continue
            pages.append(parse_person_page(slug, text))
        return tuple(sorted(pages, key=lambda page: (page.name, page.slug)))


__all__ = ["PeopleDirectory"]
