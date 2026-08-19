"""Auto-generated surface skeleton for upstream ``session/session-persistence-jsonl/src/format.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-persistence-jsonl/src/format.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "HeaderLine",
    "JsonlCompression",
    "SessionLogScanner",
    "encodeSegment",
    "eventLines",
    "fromHeaderLine",
    "logPath",
    "logSuffix",
    "parseHeaderMeta",
    "projectDir",
    "projectKey",
    "scanLog",
    "sessionDir",
    "toHeaderLine",
]

JsonlCompression: TypeAlias = object  # port: surface stub

def encodeSegment(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``encodeSegment``."""
    raise NotImplementedError("port encodeSegment from session/session-persistence-jsonl/src/format.ts")

def eventLines(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``eventLines``."""
    raise NotImplementedError("port eventLines from session/session-persistence-jsonl/src/format.ts")

def fromHeaderLine(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``fromHeaderLine``."""
    raise NotImplementedError("port fromHeaderLine from session/session-persistence-jsonl/src/format.ts")

def logPath(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``logPath``."""
    raise NotImplementedError("port logPath from session/session-persistence-jsonl/src/format.ts")

def logSuffix(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``logSuffix``."""
    raise NotImplementedError("port logSuffix from session/session-persistence-jsonl/src/format.ts")

def parseHeaderMeta(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseHeaderMeta``."""
    raise NotImplementedError("port parseHeaderMeta from session/session-persistence-jsonl/src/format.ts")

def projectDir(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``projectDir``."""
    raise NotImplementedError("port projectDir from session/session-persistence-jsonl/src/format.ts")

def projectKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``projectKey``."""
    raise NotImplementedError("port projectKey from session/session-persistence-jsonl/src/format.ts")

def scanLog(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scanLog``."""
    raise NotImplementedError("port scanLog from session/session-persistence-jsonl/src/format.ts")

def sessionDir(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sessionDir``."""
    raise NotImplementedError("port sessionDir from session/session-persistence-jsonl/src/format.ts")

def toHeaderLine(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``toHeaderLine``."""
    raise NotImplementedError("port toHeaderLine from session/session-persistence-jsonl/src/format.ts")

class SessionLogScanner:
    """Surface stub for upstream class ``SessionLogScanner``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionLogScanner.__init__ from session/session-persistence-jsonl/src/format.ts")

class HeaderLine(Protocol):
    """Surface stub for upstream interface ``HeaderLine``."""
    pass
