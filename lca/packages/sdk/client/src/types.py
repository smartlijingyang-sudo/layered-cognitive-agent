"""Auto-generated surface skeleton for upstream ``sdk/client/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sdk/client/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ContentBlock",
    "DeepSeekHarnessOptions",
    "HarnessClientOptions",
    "HarnessNotification",
    "NotificationFilter",
    "RunResult",
]

ContentBlock: TypeAlias = object  # port: surface stub

NotificationFilter: TypeAlias = object  # port: surface stub

class DeepSeekHarnessOptions(Protocol):
    """Surface stub for upstream interface ``DeepSeekHarnessOptions``."""
    pass

class HarnessClientOptions(Protocol):
    """Surface stub for upstream interface ``HarnessClientOptions``."""
    pass

class HarnessNotification(Protocol):
    """Surface stub for upstream interface ``HarnessNotification``."""
    pass

class RunResult(Protocol):
    """Surface stub for upstream interface ``RunResult``."""
    pass
