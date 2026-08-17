"""Auto-generated surface skeleton for upstream ``context/session-reference/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``context/session-reference/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PreparedReferencedMessage",
    "ReferencedConversationItem",
    "SessionReferenceCandidate",
    "SessionReferenceInput",
    "SessionReferenceSource",
]

class PreparedReferencedMessage(Protocol):
    """Surface stub for upstream interface ``PreparedReferencedMessage``."""
    pass

class ReferencedConversationItem(Protocol):
    """Surface stub for upstream interface ``ReferencedConversationItem``."""
    pass

class SessionReferenceCandidate(Protocol):
    """Surface stub for upstream interface ``SessionReferenceCandidate``."""
    pass

class SessionReferenceInput(Protocol):
    """Surface stub for upstream interface ``SessionReferenceInput``."""
    pass

class SessionReferenceSource(Protocol):
    """Surface stub for upstream interface ``SessionReferenceSource``."""
    pass
