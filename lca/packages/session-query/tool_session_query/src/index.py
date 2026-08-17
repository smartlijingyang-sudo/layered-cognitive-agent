"""Auto-generated surface skeleton for upstream ``session-query/tool-session-query/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session-query/tool-session-query/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "DEFAULT_MAX_SEARCH_RESULTS",
    "DEFAULT_SEARCH_TIMEOUT_MS",
    "apply",
    "inject",
    "name",
]

DEFAULT_MAX_SEARCH_RESULTS = None  # port: surface stub

DEFAULT_SEARCH_TIMEOUT_MS = None  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from session-query/tool-session-query/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
