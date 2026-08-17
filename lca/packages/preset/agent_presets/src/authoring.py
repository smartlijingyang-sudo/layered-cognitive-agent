"""Auto-generated surface skeleton for upstream ``preset/agent-presets/src/authoring.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``preset/agent-presets/src/authoring.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "InvalidPresetIdError",
    "PresetExistsError",
    "PresetNotWritableError",
    "copyComposition",
    "deleteComposition",
    "readComposition",
    "writableRoot",
]

def copyComposition(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``copyComposition``."""
    raise NotImplementedError("port copyComposition from preset/agent-presets/src/authoring.ts")

def deleteComposition(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deleteComposition``."""
    raise NotImplementedError("port deleteComposition from preset/agent-presets/src/authoring.ts")

def readComposition(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readComposition``."""
    raise NotImplementedError("port readComposition from preset/agent-presets/src/authoring.ts")

def writableRoot(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``writableRoot``."""
    raise NotImplementedError("port writableRoot from preset/agent-presets/src/authoring.ts")

class InvalidPresetIdError:
    """Surface stub for upstream class ``InvalidPresetIdError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port InvalidPresetIdError.__init__ from preset/agent-presets/src/authoring.ts")

class PresetExistsError:
    """Surface stub for upstream class ``PresetExistsError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PresetExistsError.__init__ from preset/agent-presets/src/authoring.ts")

class PresetNotWritableError:
    """Surface stub for upstream class ``PresetNotWritableError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PresetNotWritableError.__init__ from preset/agent-presets/src/authoring.ts")
