"""Refresh a role profile's standing-file backstory from disk.

``persona_from_home`` builds the backstory once at run start. This use case
re-reads the five standing files on later turns so a change on disk (or a
compaction that re-injects them) reaches the model without restarting the
run. It reads through the ``FileStore`` port, so the filesystem backend is
replaceable without touching the assembly logic.
"""

from __future__ import annotations

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.standing import (
    STANDING_ORDER,
    assemble_standing,
)
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore

_BACKSTORY_BUDGET = 3000


def refresh_standing_backstory(home_path: str, fallback: str) -> str:
    """Reassemble the standing-file backstory from ``home_path`` on disk.

    Returns ``fallback`` when the home directory is missing or unreadable,
    so a transient read failure never blanks the role identity.
    """

    store: FileStore = DiskFileStore(home_path)
    documents: list[tuple[str, str]] = []
    for name in STANDING_ORDER:
        try:
            text = store.read_text(name)
        except OSError:
            text = ""
        if name == "AGENTS.md" and text.strip():
            text = "## 工作约定（AGENTS.md）\n" + text.strip()
        documents.append((name, text))
    refreshed = assemble_standing(documents, budget_chars=_BACKSTORY_BUDGET)
    return refreshed if refreshed else fallback


__all__ = ["refresh_standing_backstory"]
