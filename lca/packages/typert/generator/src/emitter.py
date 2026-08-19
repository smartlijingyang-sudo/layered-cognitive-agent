"""Auto-generated surface skeleton for upstream ``typert/generator/src/emitter.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``typert/generator/src/emitter.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "FaceModelEmitter",
    "ModelEmitResult",
    "RemoteModelEmitResult",
    "TypertEmitError",
]

class FaceModelEmitter:
    """Surface stub for upstream class ``FaceModelEmitter``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port FaceModelEmitter.__init__ from typert/generator/src/emitter.ts")

class TypertEmitError:
    """Surface stub for upstream class ``TypertEmitError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TypertEmitError.__init__ from typert/generator/src/emitter.ts")

class ModelEmitResult(Protocol):
    """Surface stub for upstream interface ``ModelEmitResult``."""
    pass

class RemoteModelEmitResult(Protocol):
    """Surface stub for upstream interface ``RemoteModelEmitResult``."""
    pass
