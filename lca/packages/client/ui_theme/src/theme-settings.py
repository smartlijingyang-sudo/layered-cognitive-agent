"""Auto-generated surface skeleton for upstream ``client/ui-theme/src/theme-settings.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-theme/src/theme-settings.ts``
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
    "ThemeSettingsSchema",
    "isThemePreference",
]

ThemePreference: TypeAlias = object  # port: surface stub

DEFAULT_PREFERENCE = None  # port: surface stub

THEME_PREFERENCES = None  # port: surface stub

THEME_PREFERENCE_FIELD = None  # port: surface stub

THEME_SETTINGS_NAMESPACE = None  # port: surface stub

ThemeSettingsSchema = None  # port: surface stub

def isThemePreference(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isThemePreference``."""
    raise NotImplementedError("port isThemePreference from client/ui-theme/src/theme-settings.ts")

class ThemeSettings(Protocol):
    """Surface stub for upstream interface ``ThemeSettings``."""
    pass
