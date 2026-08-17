"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/contract/conversation.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/contract/conversation.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ChatConversationViewNode",
    "ConversationContextReader",
    "ConversationEventInput",
    "ConversationLocation",
    "ConversationLocationData",
    "ConversationLocationDataScope",
    "ConversationLocationDataStore",
    "ConversationMatch",
    "ConversationMatchResult",
    "ConversationNodeContext",
    "ConversationNodeDefinition",
    "ConversationPreviousContext",
    "ConversationPublication",
    "ConversationStepDataMap",
    "ConversationTimelineSnapshot",
    "ConversationTurnDataMap",
    "ConversationViewBuilder",
    "ConversationViewDefinition",
    "ConversationViewNode",
    "ConversationViewSnapshotMap",
    "ConversationViewSnapshotStore",
    "StepLocation",
    "TurnLocation",
    "conversationContextKey",
]

ConversationLocation: TypeAlias = object  # port: surface stub

ConversationLocationData: TypeAlias = object  # port: surface stub

ConversationLocationDataScope: TypeAlias = object  # port: surface stub

ConversationPublication: TypeAlias = object  # port: surface stub

def conversationContextKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``conversationContextKey``."""
    raise NotImplementedError("port conversationContextKey from client/runtime/src/client/contract/conversation.ts")

class ChatConversationViewNode(Protocol):
    """Surface stub for upstream interface ``ChatConversationViewNode``."""
    pass

class ConversationContextReader(Protocol):
    """Surface stub for upstream interface ``ConversationContextReader``."""
    pass

class ConversationEventInput(Protocol):
    """Surface stub for upstream interface ``ConversationEventInput``."""
    pass

class ConversationLocationDataStore(Protocol):
    """Surface stub for upstream interface ``ConversationLocationDataStore``."""
    pass

class ConversationMatch(Protocol):
    """Surface stub for upstream interface ``ConversationMatch``."""
    pass

class ConversationMatchResult(Protocol):
    """Surface stub for upstream interface ``ConversationMatchResult``."""
    pass

class ConversationNodeContext(Protocol):
    """Surface stub for upstream interface ``ConversationNodeContext``."""
    pass

class ConversationNodeDefinition(Protocol):
    """Surface stub for upstream interface ``ConversationNodeDefinition``."""
    pass

class ConversationPreviousContext(Protocol):
    """Surface stub for upstream interface ``ConversationPreviousContext``."""
    pass

class ConversationStepDataMap(Protocol):
    """Surface stub for upstream interface ``ConversationStepDataMap``."""
    pass

class ConversationTimelineSnapshot(Protocol):
    """Surface stub for upstream interface ``ConversationTimelineSnapshot``."""
    pass

class ConversationTurnDataMap(Protocol):
    """Surface stub for upstream interface ``ConversationTurnDataMap``."""
    pass

class ConversationViewBuilder(Protocol):
    """Surface stub for upstream interface ``ConversationViewBuilder``."""
    pass

class ConversationViewDefinition(Protocol):
    """Surface stub for upstream interface ``ConversationViewDefinition``."""
    pass

class ConversationViewNode(Protocol):
    """Surface stub for upstream interface ``ConversationViewNode``."""
    pass

class ConversationViewSnapshotMap(Protocol):
    """Surface stub for upstream interface ``ConversationViewSnapshotMap``."""
    pass

class ConversationViewSnapshotStore(Protocol):
    """Surface stub for upstream interface ``ConversationViewSnapshotStore``."""
    pass

class StepLocation(Protocol):
    """Surface stub for upstream interface ``StepLocation``."""
    pass

class TurnLocation(Protocol):
    """Surface stub for upstream interface ``TurnLocation``."""
    pass
