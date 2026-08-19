"""Auto-generated surface skeleton for upstream ``jobs/jobs-local/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``jobs/jobs-local/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "TASK_WAIT_TIMEOUT",
    "Config",
    "LocalJobRegistry",
]

TASK_WAIT_TIMEOUT = None  # port: surface stub

class LocalJobRegistry:
    """Surface stub for upstream class ``LocalJobRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LocalJobRegistry.__init__ from jobs/jobs-local/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
