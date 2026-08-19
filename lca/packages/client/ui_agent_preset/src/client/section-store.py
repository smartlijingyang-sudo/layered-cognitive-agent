"""Auto-generated surface skeleton for upstream ``client/ui-agent-preset/src/client/section-store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-agent-preset/src/client/section-store.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "AgentPresetSectionController",
    "AgentPresetSectionState",
    "CopyDraft",
    "PresetRow",
    "PresetView",
    "draftBlocker",
]

def draftBlocker(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``draftBlocker``."""
    raise NotImplementedError("port draftBlocker from client/ui-agent-preset/src/client/section-store.ts")

class AgentPresetSectionController:
    """Surface stub for upstream class ``AgentPresetSectionController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AgentPresetSectionController.__init__ from client/ui-agent-preset/src/client/section-store.ts")

class AgentPresetSectionState(Protocol):
    """Surface stub for upstream interface ``AgentPresetSectionState``."""
    pass

class CopyDraft(Protocol):
    """Surface stub for upstream interface ``CopyDraft``."""
    pass

class PresetRow(Protocol):
    """Surface stub for upstream interface ``PresetRow``."""
    pass

class PresetView(Protocol):
    """Surface stub for upstream interface ``PresetView``."""
    pass
