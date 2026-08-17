"""Auto-generated surface skeleton for upstream ``context/agent-instructions/src/config.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``context/agent-instructions/src/config.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "ResolvedConfig",
    "ResolvedDiscoveryConfig",
    "resolveConfig",
    "resolveDiscoveryConfig",
    "workspaceBaselineIdentity",
]

def resolveConfig(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveConfig``."""
    raise NotImplementedError("port resolveConfig from context/agent-instructions/src/config.ts")

def resolveDiscoveryConfig(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveDiscoveryConfig``."""
    raise NotImplementedError("port resolveDiscoveryConfig from context/agent-instructions/src/config.ts")

def workspaceBaselineIdentity(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``workspaceBaselineIdentity``."""
    raise NotImplementedError("port workspaceBaselineIdentity from context/agent-instructions/src/config.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class ResolvedConfig(Protocol):
    """Surface stub for upstream interface ``ResolvedConfig``."""
    pass

class ResolvedDiscoveryConfig(Protocol):
    """Surface stub for upstream interface ``ResolvedDiscoveryConfig``."""
    pass
