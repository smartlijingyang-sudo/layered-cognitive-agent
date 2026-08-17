"""Auto-generated surface skeleton for upstream ``session/session-persistence-jsonl/src/zstd.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-persistence-jsonl/src/zstd.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ZstdFrameDecoder",
    "ZstdFrameRange",
    "ZstdFrameScan",
    "compressZstdFrame",
    "createZstdFrameDecoder",
    "decompressZstdFrame",
    "decompressZstdPrefix",
    "scanZstdFrames",
]

def compressZstdFrame(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``compressZstdFrame``."""
    raise NotImplementedError("port compressZstdFrame from session/session-persistence-jsonl/src/zstd.ts")

def createZstdFrameDecoder(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createZstdFrameDecoder``."""
    raise NotImplementedError("port createZstdFrameDecoder from session/session-persistence-jsonl/src/zstd.ts")

def decompressZstdFrame(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decompressZstdFrame``."""
    raise NotImplementedError("port decompressZstdFrame from session/session-persistence-jsonl/src/zstd.ts")

def decompressZstdPrefix(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decompressZstdPrefix``."""
    raise NotImplementedError("port decompressZstdPrefix from session/session-persistence-jsonl/src/zstd.ts")

def scanZstdFrames(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scanZstdFrames``."""
    raise NotImplementedError("port scanZstdFrames from session/session-persistence-jsonl/src/zstd.ts")

class ZstdFrameDecoder(Protocol):
    """Surface stub for upstream interface ``ZstdFrameDecoder``."""
    pass

class ZstdFrameRange(Protocol):
    """Surface stub for upstream interface ``ZstdFrameRange``."""
    pass

class ZstdFrameScan(Protocol):
    """Surface stub for upstream interface ``ZstdFrameScan``."""
    pass
