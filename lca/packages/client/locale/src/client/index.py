"""Auto-generated surface skeleton for upstream ``client/locale/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/locale/src/client/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "COMMON_NS",
    "CommonKey",
    "FALLBACK_LOCALE",
    "LanguageOptionRow",
    "LanguageRowComponentProps",
    "LanguageRowInjected",
    "LanguageRowState",
    "LocaleDefinition",
    "LocaleDict",
    "LocaleId",
    "LocaleRuntime",
    "LocaleSettings",
    "LocaleSnapshot",
    "SETTINGS_NS",
    "Translate",
    "TranslateNS",
    "apply",
    "inject",
]

CommonKey: TypeAlias = object  # port: surface stub

LanguageOptionRow: TypeAlias = object  # port: surface stub

LanguageRowComponentProps: TypeAlias = object  # port: surface stub

LanguageRowInjected: TypeAlias = object  # port: surface stub

LanguageRowState: TypeAlias = object  # port: surface stub

LocaleDict: TypeAlias = object  # port: surface stub

LocaleId: TypeAlias = object  # port: surface stub

LocaleSettings: TypeAlias = object  # port: surface stub

Translate: TypeAlias = object  # port: surface stub

TranslateNS: TypeAlias = object  # port: surface stub

COMMON_NS = None  # port: surface stub

FALLBACK_LOCALE = None  # port: surface stub

SETTINGS_NS = None  # port: surface stub

inject = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/locale/src/client/index.ts")

class LocaleRuntime:
    """Surface stub for upstream class ``LocaleRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LocaleRuntime.__init__ from client/locale/src/client/index.ts")

class LocaleDefinition(Protocol):
    """Surface stub for upstream interface ``LocaleDefinition``."""
    pass

class LocaleSnapshot(Protocol):
    """Surface stub for upstream interface ``LocaleSnapshot``."""
    pass
