"""Refresh a role profile's standing-file backstory from disk.

``persona_from_home`` builds the backstory once at run start. This use case
re-reads the standing files named by the home layout on later turns so a
change on disk reaches the model without restarting the run. Tier 1 platform
files (``layout.platform_files``, resolved against ``get_lca_home()``) are
read first and always injected whole, outside any budget, so one platform
rule reaches every assistant; a missing platform file is skipped silently.
Tier 2/3 files are read through the ``FileStore`` port, so the filesystem
backend is replaceable without touching the assembly logic.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.layout import (
    ContextLayout,
    layout_for_home,
)
from lca.infrastructure.memory.contextfiles.domain.standing import assemble_standing
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore
from lca.infrastructure.path.locator import get_lca_home


def read_platform_documents(
    layout: ContextLayout,
    root: str | Path,
) -> list[tuple[str, str]]:
    """Read tier 1 platform standing files from ``root``.

    A missing file is skipped silently (fail-soft). Each body is stamped with
    ``layout.platform_heading`` so the model sees the platform provenance.
    """

    store = DiskFileStore(root)
    documents: list[tuple[str, str]] = []
    for name in layout.platform_files:
        try:
            text = store.read_text(name)
        except OSError:
            continue
        if text.strip():
            heading = layout.platform_heading.format(name=name)
            documents.append((name, f"{heading}\n{text.strip()}"))
    return documents


def read_standing_documents(
    home_path: str | Path,
    layout: ContextLayout,
    *,
    platform_root: str | Path | None = None,
) -> list[tuple[str, str]]:
    """Read tier 1 platform files, then assistant-private standing files."""

    root = platform_root if platform_root is not None else get_lca_home()
    documents = read_platform_documents(layout, root)
    store: FileStore = DiskFileStore(home_path)
    for name in layout.standing_files:
        try:
            text = store.read_text(name)
        except OSError:
            text = ""
        if name == layout.agents_file and text.strip():
            text = f"{layout.agents_heading}\n{text.strip()}"
        documents.append((name, text))
    return documents


def refresh_standing_backstory(
    home_path: str,
    fallback: str,
    *,
    platform_root: str | Path | None = None,
) -> str:
    """Reassemble the standing-file backstory from ``home_path`` on disk.

    Returns ``fallback`` when the home directory is missing or unreadable,
    so a transient read failure never blanks the role identity.
    """

    layout = layout_for_home(home_path)
    documents = read_standing_documents(home_path, layout, platform_root=platform_root)
    refreshed = assemble_standing(
        documents,
        budget_chars=layout.backstory_budget_chars,
        order=[name for name, _ in documents],
        platform_files=layout.platform_files,
        protected_files=layout.protected_files,
        protected_budget_chars=layout.protected_budget_chars,
    )
    return refreshed if refreshed else fallback


__all__ = [
    "read_platform_documents",
    "read_standing_documents",
    "refresh_standing_backstory",
]
