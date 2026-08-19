"""Auto-generated surface skeleton for upstream ``client/locale/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/locale/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "LOCALE_IDS",
    "LOCALE_PREFERENCE_FIELD",
    "LOCALE_SETTINGS_NAMESPACE",
    "LocaleId",
    "LocaleSettings",
    "apply",
]

LocaleId: TypeAlias = object  # port: surface stub

LocaleSettings: TypeAlias = object  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/locale/src/index.ts")

LOCALE_IDS = None  # port: surface stub (reexport)

LOCALE_PREFERENCE_FIELD = None  # port: surface stub (reexport)

LOCALE_SETTINGS_NAMESPACE = None  # port: surface stub (reexport)
