"""Auto-generated surface skeleton for upstream ``client/ui-permission-presets/src/client/settings-store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-permission-presets/src/client/settings-store.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "PERMISSION_SETTINGS_NS",
    "PermissionDefaultOption",
    "PermissionPresetSettingsController",
    "PermissionSettingsState",
    "permissionDefaultOf",
    "refreshPermissionIfLoaded",
]

PERMISSION_SETTINGS_NS = None  # port: surface stub

def permissionDefaultOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``permissionDefaultOf``."""
    raise NotImplementedError("port permissionDefaultOf from client/ui-permission-presets/src/client/settings-store.ts")

def refreshPermissionIfLoaded(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``refreshPermissionIfLoaded``."""
    raise NotImplementedError("port refreshPermissionIfLoaded from client/ui-permission-presets/src/client/settings-store.ts")

class PermissionPresetSettingsController:
    """Surface stub for upstream class ``PermissionPresetSettingsController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PermissionPresetSettingsController.__init__ from client/ui-permission-presets/src/client/settings-store.ts")

class PermissionDefaultOption(Protocol):
    """Surface stub for upstream interface ``PermissionDefaultOption``."""
    pass

class PermissionSettingsState(Protocol):
    """Surface stub for upstream interface ``PermissionSettingsState``."""
    pass
