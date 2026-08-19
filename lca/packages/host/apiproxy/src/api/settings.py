"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/api/settings.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/api/settings.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SettingsApi",
    "SettingsNamespaceView",
    "SettingsPathOpView",
    "SettingsSecretView",
]

SettingsPathOpView: TypeAlias = object  # port: surface stub

class SettingsApi(Protocol):
    """Surface stub for upstream interface ``SettingsApi``."""
    pass

class SettingsNamespaceView(Protocol):
    """Surface stub for upstream interface ``SettingsNamespaceView``."""
    pass

class SettingsSecretView(Protocol):
    """Surface stub for upstream interface ``SettingsSecretView``."""
    pass
