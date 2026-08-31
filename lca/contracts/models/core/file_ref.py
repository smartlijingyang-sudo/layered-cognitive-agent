"""FileRef — single SSOT for "a file, by stable identity, on the current plane".

ADR-0121. Replaces naked path / filename / download URL strings at every
prompt-render, tool-dispatch, and file-store boundary.

Lifecycles:

  user_upload        — uploaded by the human (lobehub UI) before the turn.
  sandbox_init       — staged into the sandbox guest by LCA bootstrap.
  inbox_staged       — copied into the machine inbox by LCA bootstrap.
  generated          — produced by a tool during the current run.

``target_key`` is opaque (use it as a dict key, do not parse it). The
``display_path`` is what humans / LLM see. The ``process_path`` is what the
current execution plane can actually open; it changes when ``kind`` flips.

``file_url`` is a ``file:`` URI for the host — used for cross-plane references,
never for in-plane execution.

``source`` records which subsystem minted this ref so journal / debug surfaces
can blame the right plugin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FileRefKind = Literal["user_upload", "sandbox_init", "inbox_staged", "generated"]
FileRefSource = Literal[
    "lobehub_upload",
    "sandbox_bootstrap",
    "machine_stage",
    "tool_export",
    "inline_text",
]


@dataclass(frozen=True)
class FileRef:
    """A file referenced by stable identity; resolved on demand per plane."""

    kind: FileRefKind
    target_key: str
    display_path: str
    process_path: str
    file_url: str
    mime_type: str
    size_bytes: int
    source: FileRefSource
    attachment_id: str | None = None

    def is_resolved(self) -> bool:
        """True when ``process_path`` is set and non-empty."""
        return bool(self.process_path)


__all__ = ["FileRef", "FileRefKind", "FileRefSource"]
