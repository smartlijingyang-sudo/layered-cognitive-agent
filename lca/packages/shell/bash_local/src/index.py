"""Auto-generated surface skeleton for upstream ``shell/bash-local/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``shell/bash-local/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "ENV_OVERRIDES",
    "Config",
    "LocalBashExecutor",
    "assertServiceableBashConfig",
]

ENV_OVERRIDES = None  # port: surface stub

def assertServiceableBashConfig(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertServiceableBashConfig``."""
    raise NotImplementedError("port assertServiceableBashConfig from shell/bash-local/src/index.ts")

class LocalBashExecutor:
    """Surface stub for upstream class ``LocalBashExecutor``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LocalBashExecutor.__init__ from shell/bash-local/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
