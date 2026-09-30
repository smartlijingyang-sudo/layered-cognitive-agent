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
        """Create or replace one page, then rewrite the index.

        A replaced page keeps its intimacy score so the dream pipeline's
        relationship ordering survives later ``person_note`` edits.
        """

        page_slug = slug_for(slug or name)
        page = NamedPage(
            slug=page_slug,
            name=name.strip(),
            body=body.strip(),
            intimacy=self._intimacy_of(page_slug),
        )
        if not page.name or not page.body:
            raise ValueError("name and body are required")
        self._store.atomic_replace(self._page_path(page.slug), render_person_page(page))
        pages = self.list()
        self._store.atomic_replace(self._index_path(), render_index(pages, heading=self._heading))
        logger.info("page wrote slug=%s path=%s", page.slug, self._directory)
        if self._publisher is not None and self._event_for is not None:
            self._publisher.publish(self._event_for(slug=page.slug, name=page.name))
        return page

    def _intimacy_of(self, slug: str) -> float:
        """Return the intimacy stored on an existing page, or 0.0."""

        try:
            text = self._store.read_text(self._page_path(slug))
        except OSError:
            return 0.0
        return parse_person_page(slug, text).intimacy

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

    def set_intimacy(self, slug: str, score: float) -> NamedPage | None:
        """Update one page's intimacy score and always refresh the index.

        Returns the updated page, or ``None`` when no such page exists. The
        index is rewritten even when the score is unchanged so a page that
        was created directly on disk still gets its index.
        """

        try:
            text = self._store.read_text(self._page_path(slug))
        except OSError:
            return None
        page = parse_person_page(slug, text)
        from dataclasses import replace

        updated = replace(page, intimacy=max(0.0, float(score)))
        self._store.atomic_replace(self._page_path(slug), render_person_page(updated))
        pages = self.list()
        self._store.atomic_replace(self._index_path(), render_index(pages, heading=self._heading))
        return updated

    def _page_path(self, slug: str) -> str:
        return f"{self._directory}/{slug}.md"

    def _index_path(self) -> str:
        return f"{self._directory}/{self._index_name}"


__all__ = ["PageDirectory"]
