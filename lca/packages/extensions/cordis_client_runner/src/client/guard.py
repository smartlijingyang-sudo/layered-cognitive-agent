"""Auto-generated surface skeleton for upstream ``extensions/cordis-client-runner/src/client/guard.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-client-runner/src/client/guard.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "DynamicCordisGuardEnv",
    "DynamicCordisSlotLedgerRow",
    "dynamicCordisContext",
]

def dynamicCordisContext(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``dynamicCordisContext``."""
    raise NotImplementedError("port dynamicCordisContext from extensions/cordis-client-runner/src/client/guard.ts")

class DynamicCordisGuardEnv(Protocol):
    """Surface stub for upstream interface ``DynamicCordisGuardEnv``."""
    pass

class DynamicCordisSlotLedgerRow(Protocol):
    """Surface stub for upstream interface ``DynamicCordisSlotLedgerRow``."""
    pass
