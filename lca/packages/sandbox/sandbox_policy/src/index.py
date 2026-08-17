"""Auto-generated surface skeleton for upstream ``sandbox/sandbox-policy/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sandbox/sandbox-policy/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "SANDBOX_MODES",
    "SandboxPolicyRequest",
    "SandboxPolicyService",
    "effectiveSandboxMode",
    "setSandboxMode",
]

class SandboxPolicyService:
    """Surface stub for upstream class ``SandboxPolicyService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SandboxPolicyService.__init__ from sandbox/sandbox-policy/src/index.ts")

SANDBOX_MODES = None  # port: surface stub (reexport)

effectiveSandboxMode = None  # port: surface stub (reexport)

setSandboxMode = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class SandboxPolicyRequest(Protocol):
    """Surface stub for upstream interface ``SandboxPolicyRequest``."""
    pass
