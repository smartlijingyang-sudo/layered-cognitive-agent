"""Refresh a role profile's standing-file backstory from disk.

``persona_from_home`` builds the backstory once at run start. This loader
re-reads the five standing files on later turns so a change on disk (or a
compaction that re-injects them) reaches the model without restarting the
run. Reads are cheap and the files are small.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.standing import STANDING_ORDER, assemble_standing

_BACKSTORY_BUDGET = 3000


def refresh_standing_backstory(home_path: str, fallback: str) -> str:
    """Reassemble the standing-file backstory from ``home_path`` on disk.

    Returns ``fallback`` when the home directory is missing or unreadable,
    so a transient read failure never blanks the role identity.
    """

    home = Path(home_path)
    documents: list[tuple[str, str]] = []
    for name in STANDING_ORDER:
        try:
            text = (home / name).read_text(encoding="utf-8")
        except OSError:
            text = ""
        if name == "AGENTS.md" and text.strip():
            text = "## 工作约定（AGENTS.md）\n" + text.strip()
        documents.append((name, text))
    refreshed = assemble_standing(documents, budget_chars=_BACKSTORY_BUDGET)
    return refreshed if refreshed else fallback


__all__ = ["refresh_standing_backstory"]
