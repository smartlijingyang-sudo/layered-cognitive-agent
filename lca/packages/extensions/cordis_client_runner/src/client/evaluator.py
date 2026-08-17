"""Auto-generated surface skeleton for upstream ``extensions/cordis-client-runner/src/client/evaluator.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-client-runner/src/client/evaluator.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DYNAMIC_CLIENT_REDIRECTS",
    "DynamicCordisClosureEnv",
    "DynamicCordisEvaluatedPlugin",
    "DynamicCordisStyles",
    "evaluateClientHalf",
    "isDynamicCordisPlugin",
]

DYNAMIC_CLIENT_REDIRECTS = None  # port: surface stub

def evaluateClientHalf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``evaluateClientHalf``."""
    raise NotImplementedError("port evaluateClientHalf from extensions/cordis-client-runner/src/client/evaluator.ts")

def isDynamicCordisPlugin(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isDynamicCordisPlugin``."""
    raise NotImplementedError("port isDynamicCordisPlugin from extensions/cordis-client-runner/src/client/evaluator.ts")

class DynamicCordisStyles:
    """Surface stub for upstream class ``DynamicCordisStyles``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DynamicCordisStyles.__init__ from extensions/cordis-client-runner/src/client/evaluator.ts")

class DynamicCordisClosureEnv(Protocol):
    """Surface stub for upstream interface ``DynamicCordisClosureEnv``."""
    pass

class DynamicCordisEvaluatedPlugin(Protocol):
    """Surface stub for upstream interface ``DynamicCordisEvaluatedPlugin``."""
    pass
