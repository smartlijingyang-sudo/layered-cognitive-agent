"""Auto-generated surface skeleton for upstream ``settings/settings-file/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``settings/settings-file/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "FileSettingsProvider",
    "resolveSpec",
]

def resolveSpec(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveSpec``."""
    raise NotImplementedError("port resolveSpec from settings/settings-file/src/index.ts")

class FileSettingsProvider:
    """Surface stub for upstream class ``FileSettingsProvider``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port FileSettingsProvider.__init__ from settings/settings-file/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
