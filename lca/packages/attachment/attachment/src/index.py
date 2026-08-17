"""Auto-generated surface skeleton for upstream ``attachment/attachment/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``attachment/attachment/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AttachmentError",
    "AttachmentId",
    "AttachmentIdType",
    "AttachmentStore",
    "ImageAttachmentLimits",
    "ImageAttachmentRef",
    "ImageMediaType",
    "SaveImageAttachment",
    "StoredImageAttachment",
]

AttachmentIdType: TypeAlias = object  # port: surface stub

ImageAttachmentLimits: TypeAlias = object  # port: surface stub

ImageAttachmentRef: TypeAlias = object  # port: surface stub

ImageMediaType: TypeAlias = object  # port: surface stub

SaveImageAttachment: TypeAlias = object  # port: surface stub

StoredImageAttachment: TypeAlias = object  # port: surface stub

class AttachmentStore:
    """Surface stub for upstream class ``AttachmentStore``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AttachmentStore.__init__ from attachment/attachment/src/index.ts")

AttachmentError = None  # port: surface stub (reexport)

AttachmentId = None  # port: surface stub (reexport)
