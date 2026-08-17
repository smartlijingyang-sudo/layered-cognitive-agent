"""Auto-generated surface skeleton for upstream ``settings/settings/src/redact.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``settings/settings/src/redact.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "RedactedSecret",
    "RedactedValue",
    "redactSecrets",
]

def redactSecrets(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``redactSecrets``."""
    raise NotImplementedError("port redactSecrets from settings/settings/src/redact.ts")

class RedactedSecret(Protocol):
    """Surface stub for upstream interface ``RedactedSecret``."""
    pass

class RedactedValue(Protocol):
    """Surface stub for upstream interface ``RedactedValue``."""
    pass
