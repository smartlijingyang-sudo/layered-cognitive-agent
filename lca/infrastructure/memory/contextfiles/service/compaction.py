"""Keep standing files intact when an older prompt is reused.

The folded system prompt is replay-safe for everything around the standing
files. Those files are a live view of disk. This use case rereads them
through ``FileStore`` and replaces only the injected blocks.
"""

from __future__ import annotations

import logging

from lca.infrastructure.memory.contextfiles.domain.standing import (
    STANDING_ORDER,
    refresh_injected,
)
from lca.infrastructure.memory.contextfiles.events.publisher import StandingPreserved
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore

logger = logging.getLogger(__name__)


def preserve_standing_sections(
    text: str,
    store: FileStore,
    publisher: DomainEventPublisher | None = None,
) -> str:
    """Return ``text`` with injected standing blocks replaced from ``store``."""

    files = tuple((name, _read(store, name)) for name in STANDING_ORDER)
    refreshed = refresh_injected(text, files)
    changed = refreshed != text
    if changed:
        logger.info(
            "standing sections refreshed names=%s",
            ",".join(name for name, body in files if body.strip()),
        )
    if publisher is not None and changed:
        publisher.publish(
            StandingPreserved(
                names=tuple(name for name, body in files if body.strip()),
                changed=True,
            )
        )
    return refreshed


def _read(store: FileStore, name: str) -> str:
    try:
        return store.read_text(name)
    except OSError:
        return ""


__all__ = ["preserve_standing_sections"]
