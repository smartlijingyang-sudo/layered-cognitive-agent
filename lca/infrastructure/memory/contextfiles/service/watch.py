"""Remember the last standing-file text and report what changed.

The first poll establishes a baseline and stays quiet. A later poll returns a
unified diff for files that differ. A read failure keeps the previous copy so
a missing file is not reported as a deletion.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout
from lca.infrastructure.memory.contextfiles.events.publisher import StandingChanged
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore
from lca.infrastructure.memory.contextfiles.sync import render_standing_diff, unified_diff

logger = logging.getLogger(__name__)


class StandingCursor:
    """One assistant home's previous standing-file text."""

    def __init__(self, publisher: DomainEventPublisher | None = None) -> None:
        self._files: dict[str, str] | None = None
        self._publisher = publisher

    def poll(self, store: FileStore, *, standing_files: Sequence[str] | None = None) -> str:
        """Return the diff since the previous poll, or an empty string."""

        names = (
            packaged_layout().standing_files if standing_files is None else tuple(standing_files)
        )
        current = {name: _read(store, name, self._files) for name in names}
        previous = self._files
        self._files = current
        if previous is None:
            return ""
        changes: list[tuple[str, str]] = []
        for name in names:
            diff = unified_diff(name, previous.get(name, ""), current.get(name, ""))
            if not diff:
                continue
            changes.append((name, diff))
            logger.info("standing file changed path=%s", name)
            if self._publisher is not None:
                self._publisher.publish(StandingChanged(path=name, diff=diff))
        return render_standing_diff(changes)


def _read(store: FileStore, name: str, previous: dict[str, str] | None) -> str:
    try:
        return store.read_text(name)
    except OSError:
        if previous is not None and name in previous:
            return previous[name]
        return ""


__all__ = ["StandingCursor"]
