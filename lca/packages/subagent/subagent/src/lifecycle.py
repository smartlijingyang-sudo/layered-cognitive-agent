"""Auto-generated surface skeleton for upstream ``subagent/subagent/src/lifecycle.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent/src/lifecycle.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ActivationObserver",
    "ActivationTerminal",
    "LifecycleEmitter",
    "createActivationObserver",
    "createLifecycleEmitter",
    "observeRun",
]

LifecycleEmitter: TypeAlias = object  # port: surface stub

def createActivationObserver(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createActivationObserver``."""
    raise NotImplementedError("port createActivationObserver from subagent/subagent/src/lifecycle.ts")

def createLifecycleEmitter(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createLifecycleEmitter``."""
    raise NotImplementedError("port createLifecycleEmitter from subagent/subagent/src/lifecycle.ts")

def observeRun(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``observeRun``."""
    raise NotImplementedError("port observeRun from subagent/subagent/src/lifecycle.ts")

class ActivationObserver(Protocol):
    """Surface stub for upstream interface ``ActivationObserver``."""
    pass

class ActivationTerminal(Protocol):
    """Surface stub for upstream interface ``ActivationTerminal``."""
    pass
