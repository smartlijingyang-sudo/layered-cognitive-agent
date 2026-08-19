"""Auto-generated surface skeleton for upstream ``util/atomic-write/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``util/atomic-write/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "WriteFileAtomicOptions",
    "withFileLock",
    "writeFileAtomic",
]

def withFileLock(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``withFileLock``."""
    raise NotImplementedError("port withFileLock from util/atomic-write/src/index.ts")

def writeFileAtomic(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``writeFileAtomic``."""
    raise NotImplementedError("port writeFileAtomic from util/atomic-write/src/index.ts")

class WriteFileAtomicOptions(Protocol):
    """Surface stub for upstream interface ``WriteFileAtomicOptions``."""
    pass
