"""Auto-generated surface skeleton for upstream ``llm/llm/src/message.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm/src/message.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CONTEXT_SUMMARY_MAX_CHARS",
    "AssistantMessage",
    "AssistantProvenance",
    "ContextForm",
    "ContextFormed",
    "ContextSnapshotSection",
    "Message",
    "MessageSource",
    "MessageSourceMap",
    "ModelMessageSource",
    "ToolMessageSource",
    "ToolResultMessage",
    "ToolResultMessageInput",
    "UserMessage",
    "boundContextSummary",
    "createAssistantMessage",
    "createMessage",
    "createToolResultMessage",
    "createUserMessage",
    "freezeMessage",
    "isTokenDelta",
]

ContextForm: TypeAlias = object  # port: surface stub

ContextFormed: TypeAlias = object  # port: surface stub

MessageSource: TypeAlias = object  # port: surface stub

CONTEXT_SUMMARY_MAX_CHARS = None  # port: surface stub

def boundContextSummary(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``boundContextSummary``."""
    raise NotImplementedError("port boundContextSummary from llm/llm/src/message.ts")

def createAssistantMessage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createAssistantMessage``."""
    raise NotImplementedError("port createAssistantMessage from llm/llm/src/message.ts")

def createMessage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createMessage``."""
    raise NotImplementedError("port createMessage from llm/llm/src/message.ts")

def createToolResultMessage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createToolResultMessage``."""
    raise NotImplementedError("port createToolResultMessage from llm/llm/src/message.ts")

def createUserMessage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createUserMessage``."""
    raise NotImplementedError("port createUserMessage from llm/llm/src/message.ts")

def freezeMessage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``freezeMessage``."""
    raise NotImplementedError("port freezeMessage from llm/llm/src/message.ts")

def isTokenDelta(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isTokenDelta``."""
    raise NotImplementedError("port isTokenDelta from llm/llm/src/message.ts")

class AssistantMessage(Protocol):
    """Surface stub for upstream interface ``AssistantMessage``."""
    pass

class AssistantProvenance(Protocol):
    """Surface stub for upstream interface ``AssistantProvenance``."""
    pass

class ContextSnapshotSection(Protocol):
    """Surface stub for upstream interface ``ContextSnapshotSection``."""
    pass

class Message(Protocol):
    """Surface stub for upstream interface ``Message``."""
    pass

class MessageSourceMap(Protocol):
    """Surface stub for upstream interface ``MessageSourceMap``."""
    pass

class ModelMessageSource(Protocol):
    """Surface stub for upstream interface ``ModelMessageSource``."""
    pass

class ToolMessageSource(Protocol):
    """Surface stub for upstream interface ``ToolMessageSource``."""
    pass

class ToolResultMessage(Protocol):
    """Surface stub for upstream interface ``ToolResultMessage``."""
    pass

class ToolResultMessageInput(Protocol):
    """Surface stub for upstream interface ``ToolResultMessageInput``."""
    pass

class UserMessage(Protocol):
    """Surface stub for upstream interface ``UserMessage``."""
    pass
