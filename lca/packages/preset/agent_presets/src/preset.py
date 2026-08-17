"""Auto-generated surface skeleton for upstream ``preset/agent-presets/src/preset.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``preset/agent-presets/src/preset.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AgentPreset",
    "Config",
    "PRESET_ID",
    "PresetMountError",
    "PresetRoot",
    "PresetTrust",
    "UnknownPresetError",
]

PresetTrust: TypeAlias = object  # port: surface stub

PRESET_ID = None  # port: surface stub

class PresetMountError:
    """Surface stub for upstream class ``PresetMountError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PresetMountError.__init__ from preset/agent-presets/src/preset.ts")

class UnknownPresetError:
    """Surface stub for upstream class ``UnknownPresetError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port UnknownPresetError.__init__ from preset/agent-presets/src/preset.ts")

class AgentPreset(Protocol):
    """Surface stub for upstream interface ``AgentPreset``."""
    pass

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class PresetRoot(Protocol):
    """Surface stub for upstream interface ``PresetRoot``."""
    pass
