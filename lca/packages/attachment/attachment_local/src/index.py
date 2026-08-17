"""Auto-generated surface skeleton for upstream ``attachment/attachment-local/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``attachment/attachment-local/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "DEFAULT_MAX_IMAGES_PER_MESSAGE",
    "DEFAULT_MAX_IMAGE_BYTES",
    "DEFAULT_MAX_IMAGE_PIXELS",
    "DEFAULT_MAX_MESSAGE_IMAGE_BYTES",
    "LocalAttachmentStore",
    "detectImage",
    "readImageFile",
    "saveImageFile",
    "validateImageFile",
]

DEFAULT_MAX_IMAGES_PER_MESSAGE = None  # port: surface stub

DEFAULT_MAX_IMAGE_BYTES = None  # port: surface stub

DEFAULT_MAX_IMAGE_PIXELS = None  # port: surface stub

DEFAULT_MAX_MESSAGE_IMAGE_BYTES = None  # port: surface stub

class LocalAttachmentStore:
    """Surface stub for upstream class ``LocalAttachmentStore``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LocalAttachmentStore.__init__ from attachment/attachment-local/src/index.ts")

detectImage = None  # port: surface stub (reexport)

readImageFile = None  # port: surface stub (reexport)

saveImageFile = None  # port: surface stub (reexport)

validateImageFile = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
