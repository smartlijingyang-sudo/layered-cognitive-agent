"""Refresh a role profile's standing-file backstory from disk.

``persona_from_home`` builds the backstory once at run start. This use case
re-reads the standing files named by the home layout on later turns so a
change on disk reaches the model without restarting the run. It reads
through the ``FileStore`` port, so the filesystem backend is replaceable
without touching the assembly logic.
"""

from __future__ import annotations

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.layout import layout_for_home
from lca.infrastructure.memory.contextfiles.domain.standing import assemble_standing
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore


def refresh_standing_backstory(home_path: str, fallback: str) -> str:
    """Reassemble the standing-file backstory from ``home_path`` on disk.

    Returns ``fallback`` when the home directory is missing or unreadable,
    so a transient read failure never blanks the role identity.
    """

    layout = layout_for_home(home_path)
    store: FileStore = DiskFileStore(home_path)
    documents: list[tuple[str, str]] = []
    for name in layout.standing_files:
        try:
            text = store.read_text(name)
        except OSError:
            text = ""
        if name == layout.agents_file and text.strip():
            text = f"{layout.agents_heading}\n{text.strip()}"
        documents.append((name, text))
    refreshed = assemble_standing(
        documents,
        budget_chars=layout.backstory_budget_chars,
        order=layout.standing_files,
    )
    return refreshed if refreshed else fallback


__all__ = ["refresh_standing_backstory"]
