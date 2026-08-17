"""Auto-generated surface skeleton for upstream ``extensions/cordis-client-runner/src/client/orchestrator.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-client-runner/src/client/orchestrator.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CordisRunActivity",
    "CordisRunFailure",
    "CordisRunHostSeam",
    "CordisRunOrchestrator",
    "CordisRunOrchestratorEnv",
    "CordisRunRequest",
    "CordisUserRunRequest",
]

CordisRunActivity: TypeAlias = object  # port: surface stub

class CordisRunOrchestrator:
    """Surface stub for upstream class ``CordisRunOrchestrator``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port CordisRunOrchestrator.__init__ from extensions/cordis-client-runner/src/client/orchestrator.ts")

class CordisRunFailure(Protocol):
    """Surface stub for upstream interface ``CordisRunFailure``."""
    pass

class CordisRunHostSeam(Protocol):
    """Surface stub for upstream interface ``CordisRunHostSeam``."""
    pass

class CordisRunOrchestratorEnv(Protocol):
    """Surface stub for upstream interface ``CordisRunOrchestratorEnv``."""
    pass

class CordisRunRequest(Protocol):
    """Surface stub for upstream interface ``CordisRunRequest``."""
    pass

class CordisUserRunRequest(Protocol):
    """Surface stub for upstream interface ``CordisUserRunRequest``."""
    pass
