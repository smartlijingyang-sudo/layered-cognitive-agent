"""Keep standing files intact when an older prompt is reused.

The folded system prompt is replay-safe for everything around the standing
files. Those files are a live view of disk. This use case rereads them
through ``FileStore`` and replaces only the injected blocks.
"""

from __future__ import annotations

import logging
from pathlib import Path

from lca.infrastructure.memory.contextfiles.domain.layout import ContextLayout, packaged_layout
from lca.infrastructure.memory.contextfiles.domain.standing import refresh_injected
from lca.infrastructure.memory.contextfiles.events.publisher import StandingPreserved
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore
from lca.infrastructure.memory.contextfiles.service.assembly import (
    read_platform_documents,
)
from lca.infrastructure.path.locator import get_lca_home

logger = logging.getLogger(__name__)


def preserve_standing_sections(
    text: str,
    store: FileStore,
    publisher: DomainEventPublisher | None = None,
    *,
    layout: ContextLayout | None = None,
    platform_root: str | Path | None = None,
) -> str:
    """Return ``text`` with injected standing blocks replaced from ``store``.

    Tier 1 platform files are refreshed from ``platform_root`` (default
    ``get_lca_home()``) so a prompt reuse never drops the platform blocks.
    """

    chosen = packaged_layout() if layout is None else layout
    root = platform_root if platform_root is not None else get_lca_home()
    files = read_platform_documents(chosen, root)
    files.extend((name, _read(store, name)) for name in chosen.standing_files)
    refreshed = refresh_injected(
        text,
        files,
        order=[name for name, _ in files],
        live_note=chosen.live_note,
    )
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
