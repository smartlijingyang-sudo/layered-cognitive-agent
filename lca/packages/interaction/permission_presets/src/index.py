"""Auto-generated surface skeleton for upstream ``interaction/permission-presets/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``interaction/permission-presets/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CUSTOM_PRESET",
    "Config",
    "KnobState",
    "PERMISSION_SETTINGS_NAMESPACE",
    "PermissionPresetService",
    "PermissionSettings",
    "PresetSpec",
    "applyKnobEvent",
    "effectivePermissionPreset",
]

CUSTOM_PRESET = None  # port: surface stub

PERMISSION_SETTINGS_NAMESPACE = None  # port: surface stub

def applyKnobEvent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``applyKnobEvent``."""
    raise NotImplementedError("port applyKnobEvent from interaction/permission-presets/src/index.ts")

def effectivePermissionPreset(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``effectivePermissionPreset``."""
    raise NotImplementedError("port effectivePermissionPreset from interaction/permission-presets/src/index.ts")

class PermissionPresetService:
    """Surface stub for upstream class ``PermissionPresetService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PermissionPresetService.__init__ from interaction/permission-presets/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class KnobState(Protocol):
    """Surface stub for upstream interface ``KnobState``."""
    pass

class PermissionSettings(Protocol):
    """Surface stub for upstream interface ``PermissionSettings``."""
    pass

class PresetSpec(Protocol):
    """Surface stub for upstream interface ``PresetSpec``."""
    pass
