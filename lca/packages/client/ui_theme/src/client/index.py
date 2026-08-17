"""Auto-generated surface skeleton for upstream ``client/ui-theme/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-theme/src/client/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AppearanceRowComponentProps",
    "AppearanceRowInjected",
    "AppearanceRowState",
    "SETTINGS_NS",
    "ThemeDefinition",
    "ThemeKey",
    "ThemePreference",
    "ThemeRuntime",
    "ThemeSettings",
    "ThemeSnapshot",
    "ThemeTokenInspection",
    "ThemeTokenModes",
    "ThemeTokenOverrides",
    "ThemeTokens",
    "apply",
    "inject",
]

AppearanceRowComponentProps: TypeAlias = object  # port: surface stub

AppearanceRowInjected: TypeAlias = object  # port: surface stub

AppearanceRowState: TypeAlias = object  # port: surface stub

ThemeKey: TypeAlias = object  # port: surface stub

ThemePreference: TypeAlias = object  # port: surface stub

ThemeSettings: TypeAlias = object  # port: surface stub

ThemeTokenOverrides: TypeAlias = object  # port: surface stub

ThemeTokens: TypeAlias = object  # port: surface stub

SETTINGS_NS = None  # port: surface stub

inject = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/ui-theme/src/client/index.ts")

class ThemeRuntime:
    """Surface stub for upstream class ``ThemeRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ThemeRuntime.__init__ from client/ui-theme/src/client/index.ts")

class ThemeDefinition(Protocol):
    """Surface stub for upstream interface ``ThemeDefinition``."""
    pass

class ThemeSnapshot(Protocol):
    """Surface stub for upstream interface ``ThemeSnapshot``."""
    pass

class ThemeTokenInspection(Protocol):
    """Surface stub for upstream interface ``ThemeTokenInspection``."""
    pass

class ThemeTokenModes(Protocol):
    """Surface stub for upstream interface ``ThemeTokenModes``."""
    pass
