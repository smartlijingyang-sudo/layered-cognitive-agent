"""Auto-generated surface skeleton for upstream ``fs/tool-fs/src/sandbox.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/tool-fs/src/sandbox.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "EscalationSchemaFields",
    "FsEscalationArgs",
    "FsSandboxController",
]

class FsSandboxController:
    """Surface stub for upstream class ``FsSandboxController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port FsSandboxController.__init__ from fs/tool-fs/src/sandbox.ts")

class EscalationSchemaFields(Protocol):
    """Surface stub for upstream interface ``EscalationSchemaFields``."""
    pass

class FsEscalationArgs(Protocol):
    """Surface stub for upstream interface ``FsEscalationArgs``."""
    pass
