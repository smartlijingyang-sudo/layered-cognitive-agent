"""Auto-generated surface skeleton for upstream ``preset/agent-presets/src/metadata.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``preset/agent-presets/src/metadata.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "METADATA_FILE",
    "PresetMetadata",
    "readPresetMetadata",
    "renderPresetMetadata",
]

METADATA_FILE = None  # port: surface stub

def readPresetMetadata(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readPresetMetadata``."""
    raise NotImplementedError("port readPresetMetadata from preset/agent-presets/src/metadata.ts")

def renderPresetMetadata(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderPresetMetadata``."""
    raise NotImplementedError("port renderPresetMetadata from preset/agent-presets/src/metadata.ts")

class PresetMetadata(Protocol):
    """Surface stub for upstream interface ``PresetMetadata``."""
    pass
