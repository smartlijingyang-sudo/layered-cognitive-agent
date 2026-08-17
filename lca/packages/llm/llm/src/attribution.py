"""Auto-generated surface skeleton for upstream ``llm/llm/src/attribution.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm/src/attribution.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "APP_IDENTITY",
    "AppIdentity",
    "attributionHeaders",
    "userAgent",
]

APP_IDENTITY = None  # port: surface stub

def attributionHeaders(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``attributionHeaders``."""
    raise NotImplementedError("port attributionHeaders from llm/llm/src/attribution.ts")

def userAgent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``userAgent``."""
    raise NotImplementedError("port userAgent from llm/llm/src/attribution.ts")

class AppIdentity(Protocol):
    """Surface stub for upstream interface ``AppIdentity``."""
    pass
