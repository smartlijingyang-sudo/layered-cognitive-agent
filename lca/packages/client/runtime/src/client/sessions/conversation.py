"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/conversation.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/conversation.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "EMPTY_CHAT_SNAPSHOT",
    "EMPTY_CONVERSATION_VIEWS",
    "AssistantBlock",
    "AssistantMessageNode",
    "AssistantProvenanceView",
    "AssistantRequestConfig",
    "AssistantTiming",
    "ChatLocationNodeIndex",
    "ChatNodeStore",
    "ChatSnapshot",
    "CommandNode",
    "CompactionSummaryNode",
    "ComposerPhase",
    "ContextMessageNode",
    "ConversationNode",
    "ConversationSnapshot",
    "LegacyConversationSlice",
    "ModelRetryNode",
    "OpenState",
    "PartialAssistant",
    "PromptError",
    "QueuedMessage",
    "RunningToolCall",
    "SteeringMessageNode",
    "TodoItem",
    "ToolCallBlock",
    "ToolResultNode",
    "TurnErrorNode",
    "TurnMaxTokensNode",
    "UnknownSurfaceNode",
    "UserMessageNode",
    "toAssistantBlock",
    "toAssistantBlocks",
]

AssistantBlock: TypeAlias = object  # port: surface stub

ComposerPhase: TypeAlias = object  # port: surface stub

ConversationNode: TypeAlias = object  # port: surface stub

ModelRetryNode: TypeAlias = object  # port: surface stub

OpenState: TypeAlias = object  # port: surface stub

TodoItem: TypeAlias = object  # port: surface stub

ToolCallBlock: TypeAlias = object  # port: surface stub

EMPTY_CHAT_SNAPSHOT = None  # port: surface stub

EMPTY_CONVERSATION_VIEWS = None  # port: surface stub

def toAssistantBlock(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``toAssistantBlock``."""
    raise NotImplementedError("port toAssistantBlock from client/runtime/src/client/sessions/conversation.ts")

def toAssistantBlocks(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``toAssistantBlocks``."""
    raise NotImplementedError("port toAssistantBlocks from client/runtime/src/client/sessions/conversation.ts")

class AssistantMessageNode(Protocol):
    """Surface stub for upstream interface ``AssistantMessageNode``."""
    pass

class AssistantProvenanceView(Protocol):
    """Surface stub for upstream interface ``AssistantProvenanceView``."""
    pass

class AssistantRequestConfig(Protocol):
    """Surface stub for upstream interface ``AssistantRequestConfig``."""
    pass

class AssistantTiming(Protocol):
    """Surface stub for upstream interface ``AssistantTiming``."""
    pass

class ChatLocationNodeIndex(Protocol):
    """Surface stub for upstream interface ``ChatLocationNodeIndex``."""
    pass

class ChatNodeStore(Protocol):
    """Surface stub for upstream interface ``ChatNodeStore``."""
    pass

class ChatSnapshot(Protocol):
    """Surface stub for upstream interface ``ChatSnapshot``."""
    pass

class CommandNode(Protocol):
    """Surface stub for upstream interface ``CommandNode``."""
    pass

class CompactionSummaryNode(Protocol):
    """Surface stub for upstream interface ``CompactionSummaryNode``."""
    pass

class ContextMessageNode(Protocol):
    """Surface stub for upstream interface ``ContextMessageNode``."""
    pass

class ConversationSnapshot(Protocol):
    """Surface stub for upstream interface ``ConversationSnapshot``."""
    pass

class LegacyConversationSlice(Protocol):
    """Surface stub for upstream interface ``LegacyConversationSlice``."""
    pass

class PartialAssistant(Protocol):
    """Surface stub for upstream interface ``PartialAssistant``."""
    pass

class PromptError(Protocol):
    """Surface stub for upstream interface ``PromptError``."""
    pass

class QueuedMessage(Protocol):
    """Surface stub for upstream interface ``QueuedMessage``."""
    pass

class RunningToolCall(Protocol):
    """Surface stub for upstream interface ``RunningToolCall``."""
    pass

class SteeringMessageNode(Protocol):
    """Surface stub for upstream interface ``SteeringMessageNode``."""
    pass

class ToolResultNode(Protocol):
    """Surface stub for upstream interface ``ToolResultNode``."""
    pass

class TurnErrorNode(Protocol):
    """Surface stub for upstream interface ``TurnErrorNode``."""
    pass

class TurnMaxTokensNode(Protocol):
    """Surface stub for upstream interface ``TurnMaxTokensNode``."""
    pass

class UnknownSurfaceNode(Protocol):
    """Surface stub for upstream interface ``UnknownSurfaceNode``."""
    pass

class UserMessageNode(Protocol):
    """Surface stub for upstream interface ``UserMessageNode``."""
    pass
