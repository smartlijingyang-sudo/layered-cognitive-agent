"""Auto-generated surface skeleton for upstream ``shell/pwsh-local/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``shell/pwsh-local/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "ENCODING_PREAMBLE",
    "ENV_OVERRIDES",
    "PwshLocalExecutor",
    "assertServiceablePwshConfig",
    "candidatePwshPaths",
    "resolvePwshPath",
]

ENCODING_PREAMBLE = None  # port: surface stub

ENV_OVERRIDES = None  # port: surface stub

def assertServiceablePwshConfig(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertServiceablePwshConfig``."""
    raise NotImplementedError("port assertServiceablePwshConfig from shell/pwsh-local/src/index.ts")

class PwshLocalExecutor:
    """Surface stub for upstream class ``PwshLocalExecutor``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PwshLocalExecutor.__init__ from shell/pwsh-local/src/index.ts")

candidatePwshPaths = None  # port: surface stub (reexport)

resolvePwshPath = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
