"""Auto-generated surface skeleton for upstream ``client/ui-theme/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-theme/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DEFAULT_PREFERENCE",
    "THEME_PREFERENCES",
    "THEME_PREFERENCE_FIELD",
    "THEME_SETTINGS_NAMESPACE",
    "ThemePreference",
    "ThemeSettings",
    "apply",
]

ThemePreference: TypeAlias = object  # port: surface stub

ThemeSettings: TypeAlias = object  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/ui-theme/src/index.ts")

DEFAULT_PREFERENCE = None  # port: surface stub (reexport)

THEME_PREFERENCES = None  # port: surface stub (reexport)

THEME_PREFERENCE_FIELD = None  # port: surface stub (reexport)

THEME_SETTINGS_NAMESPACE = None  # port: surface stub (reexport)
