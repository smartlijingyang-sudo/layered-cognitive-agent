"""Auto-generated surface skeleton for upstream ``terminal/terminal-bash/src/sanitize.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``terminal/terminal-bash/src/sanitize.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "CONTROLLED_PROMPT",
    "PROMPT_MARKER_PREFIX",
    "SanitizedChunk",
    "TerminalSanitizer",
    "normalizeTerminalText",
]

CONTROLLED_PROMPT = None  # port: surface stub

PROMPT_MARKER_PREFIX = None  # port: surface stub

def normalizeTerminalText(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``normalizeTerminalText``."""
    raise NotImplementedError("port normalizeTerminalText from terminal/terminal-bash/src/sanitize.ts")

class TerminalSanitizer:
    """Surface stub for upstream class ``TerminalSanitizer``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TerminalSanitizer.__init__ from terminal/terminal-bash/src/sanitize.ts")

class SanitizedChunk(Protocol):
    """Surface stub for upstream interface ``SanitizedChunk``."""
    pass
