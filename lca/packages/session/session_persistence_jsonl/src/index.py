"""Auto-generated surface skeleton for upstream ``session/session-persistence-jsonl/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-persistence-jsonl/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "JsonlCompression",
    "JsonlCompressionSchema",
    "JsonlSessionPersistence",
]

JsonlCompression: TypeAlias = object  # port: surface stub

JsonlCompressionSchema = None  # port: surface stub

class JsonlSessionPersistence:
    """Surface stub for upstream class ``JsonlSessionPersistence``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port JsonlSessionPersistence.__init__ from session/session-persistence-jsonl/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
