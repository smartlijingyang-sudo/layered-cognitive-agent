"""Auto-generated surface skeleton for upstream ``sdk/protocol/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sdk/protocol/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "HarnessSdkNotificationMap",
    "HarnessSdkRequestMap",
    "InitializeParams",
    "InitializeResult",
    "SdkRunStatus",
    "SessionEventNotification",
    "SessionPromptParams",
    "SessionPromptResult",
    "SessionStatusNotification",
    "SubagentFinishedNotification",
    "SubagentStartedNotification",
]

SdkRunStatus: TypeAlias = object  # port: surface stub

class HarnessSdkNotificationMap(Protocol):
    """Surface stub for upstream interface ``HarnessSdkNotificationMap``."""
    pass

class HarnessSdkRequestMap(Protocol):
    """Surface stub for upstream interface ``HarnessSdkRequestMap``."""
    pass

class InitializeParams(Protocol):
    """Surface stub for upstream interface ``InitializeParams``."""
    pass

class InitializeResult(Protocol):
    """Surface stub for upstream interface ``InitializeResult``."""
    pass

class SessionEventNotification(Protocol):
    """Surface stub for upstream interface ``SessionEventNotification``."""
    pass

class SessionPromptParams(Protocol):
    """Surface stub for upstream interface ``SessionPromptParams``."""
    pass

class SessionPromptResult(Protocol):
    """Surface stub for upstream interface ``SessionPromptResult``."""
    pass

class SessionStatusNotification(Protocol):
    """Surface stub for upstream interface ``SessionStatusNotification``."""
    pass

class SubagentFinishedNotification(Protocol):
    """Surface stub for upstream interface ``SubagentFinishedNotification``."""
    pass

class SubagentStartedNotification(Protocol):
    """Surface stub for upstream interface ``SubagentStartedNotification``."""
    pass
