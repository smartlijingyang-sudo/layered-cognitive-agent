"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/client/conversation-nodes/inbox.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/client/conversation-nodes/inbox.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "InboxState",
    "nextStepInboxDefinition",
    "nextTurnInboxDefinition",
    "registerInboxConversationNodes",
]

nextStepInboxDefinition = None  # port: surface stub

nextTurnInboxDefinition = None  # port: surface stub

def registerInboxConversationNodes(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``registerInboxConversationNodes``."""
    raise NotImplementedError("port registerInboxConversationNodes from client/ui-conversation/src/client/conversation-nodes/inbox.ts")

class InboxState(Protocol):
    """Surface stub for upstream interface ``InboxState``."""
    pass
