"""Write one named page and refresh the index from those pages.

People and groups are two folders of this same record. The directory, index
name, and heading come from the caller. A failed index write leaves the page
that just landed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from lca.infrastructure.memory.contextfiles.domain.people import (
    NamedPage,
    parse_person_page,
    render_index,
    render_person_page,
    slug_for,
)
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore

logger = logging.getLogger(__name__)


class PageDirectory:
    """Named pages under one directory of an assistant home."""

    def __init__(
        self,
        store: FileStore,
        *,
        directory: str,
        index_name: str,
        heading: str,
        publisher: DomainEventPublisher | None = None,
        event_for: Callable[..., object] | None = None,
    ) -> None:
        self._store = store
        self._directory = directory
        self._index_name = index_name
        self._heading = heading
        self._publisher = publisher
        self._event_for = event_for

    def upsert(self, name: str, body: str, *, slug: str | None = None) -> NamedPage:
        """Create or replace one page, then rewrite the index."""

        page = NamedPage(slug=slug_for(slug or name), name=name.strip(), body=body.strip())
        if not page.name or not page.body:
            raise ValueError("name and body are required")
        self._store.atomic_replace(self._page_path(page.slug), render_person_page(page))
        pages = self.list()
        self._store.atomic_replace(self._index_path(), render_index(pages, heading=self._heading))
        logger.info("page wrote slug=%s path=%s", page.slug, self._directory)
        if self._publisher is not None and self._event_for is not None:
            self._publisher.publish(self._event_for(slug=page.slug, name=page.name))
        return page

    def list(self) -> tuple[NamedPage, ...]:
        """Return pages in this directory. The index file is not a page."""

        pages: list[NamedPage] = []
        for name in self._store.list_dir(self._directory):
            if name == self._index_name or not name.endswith(".md"):
                continue
            slug = name[: -len(".md")]
            try:
                text = self._store.read_text(self._page_path(slug))
            except OSError:
                continue
            pages.append(parse_person_page(slug, text))
        return tuple(sorted(pages, key=lambda page: (page.name, page.slug)))

    def _page_path(self, slug: str) -> str:
        return f"{self._directory}/{slug}.md"

    def _index_path(self) -> str:
        return f"{self._directory}/{self._index_name}"


__all__ = ["PageDirectory"]
