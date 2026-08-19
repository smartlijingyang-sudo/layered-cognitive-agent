"""Auto-generated surface skeleton for upstream ``jobs/tool-jobs/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``jobs/tool-jobs/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CompletionDelivery",
    "Config",
    "PublicJobSnapshot",
    "apply",
    "inject",
    "name",
    "statusLine",
]

CompletionDelivery: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from jobs/tool-jobs/src/index.ts")

def statusLine(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``statusLine``."""
    raise NotImplementedError("port statusLine from jobs/tool-jobs/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class PublicJobSnapshot(Protocol):
    """Surface stub for upstream interface ``PublicJobSnapshot``."""
    pass
