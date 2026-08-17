"""Auto-generated surface skeleton for upstream ``attachment/attachment-local/src/image.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``attachment/attachment-local/src/image.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DetectedImage",
    "detectImage",
    "probeImage",
]

def detectImage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``detectImage``."""
    raise NotImplementedError("port detectImage from attachment/attachment-local/src/image.ts")

def probeImage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``probeImage``."""
    raise NotImplementedError("port probeImage from attachment/attachment-local/src/image.ts")

class DetectedImage(Protocol):
    """Surface stub for upstream interface ``DetectedImage``."""
    pass
