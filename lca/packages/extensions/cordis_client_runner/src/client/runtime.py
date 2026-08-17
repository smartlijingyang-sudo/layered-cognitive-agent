"""Auto-generated surface skeleton for upstream ``extensions/cordis-client-runner/src/client/runtime.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-client-runner/src/client/runtime.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CordisErrorDetails",
    "CordisObservable",
    "DynamicCordisClientHalf",
    "DynamicCordisLivePackage",
    "DynamicCordisLoadErrorCause",
    "DynamicCordisLoadResult",
    "DynamicCordisPackageRunner",
    "DynamicCordisRenderFailure",
    "DynamicCordisRunnerEnv",
    "errorDetails",
]

DynamicCordisLoadErrorCause: TypeAlias = object  # port: surface stub

DynamicCordisLoadResult: TypeAlias = object  # port: surface stub

def errorDetails(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``errorDetails``."""
    raise NotImplementedError("port errorDetails from extensions/cordis-client-runner/src/client/runtime.ts")

class DynamicCordisPackageRunner:
    """Surface stub for upstream class ``DynamicCordisPackageRunner``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DynamicCordisPackageRunner.__init__ from extensions/cordis-client-runner/src/client/runtime.ts")

class CordisErrorDetails(Protocol):
    """Surface stub for upstream interface ``CordisErrorDetails``."""
    pass

class CordisObservable(Protocol):
    """Surface stub for upstream interface ``CordisObservable``."""
    pass

class DynamicCordisClientHalf(Protocol):
    """Surface stub for upstream interface ``DynamicCordisClientHalf``."""
    pass

class DynamicCordisLivePackage(Protocol):
    """Surface stub for upstream interface ``DynamicCordisLivePackage``."""
    pass

class DynamicCordisRenderFailure(Protocol):
    """Surface stub for upstream interface ``DynamicCordisRenderFailure``."""
    pass

class DynamicCordisRunnerEnv(Protocol):
    """Surface stub for upstream interface ``DynamicCordisRunnerEnv``."""
    pass
