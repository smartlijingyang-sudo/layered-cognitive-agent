"""Auto-generated surface skeleton for upstream ``attachment/attachment/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``attachment/attachment/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AttachmentId",
    "ImageAttachmentLimits",
    "ImageAttachmentRef",
    "ImageMediaType",
    "SaveImageAttachment",
    "StoredImageAttachment",
]

AttachmentId: TypeAlias = object  # port: surface stub

ImageMediaType: TypeAlias = object  # port: surface stub

class ImageAttachmentLimits(Protocol):
    """Surface stub for upstream interface ``ImageAttachmentLimits``."""
    pass

class ImageAttachmentRef(Protocol):
    """Surface stub for upstream interface ``ImageAttachmentRef``."""
    pass

class SaveImageAttachment(Protocol):
    """Surface stub for upstream interface ``SaveImageAttachment``."""
    pass

class StoredImageAttachment(Protocol):
    """Surface stub for upstream interface ``StoredImageAttachment``."""
    pass
