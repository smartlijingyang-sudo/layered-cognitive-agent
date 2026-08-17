"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/client/contract/chat-nodes.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/client/contract/chat-nodes.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AssistantChatData",
    "ChatNode",
    "ChatNodeDataMap",
    "ChatNodeKind",
    "FinalAssistantChatData",
    "ManualCompactionChatData",
    "RetryChatData",
    "ToolChatData",
    "TurnTailChatData",
    "isRunningTool",
    "isSettledTool",
]

ChatNode: TypeAlias = object  # port: surface stub

ChatNodeKind: TypeAlias = object  # port: surface stub

FinalAssistantChatData: TypeAlias = object  # port: surface stub

def isRunningTool(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isRunningTool``."""
    raise NotImplementedError("port isRunningTool from client/ui-conversation/src/client/contract/chat-nodes.ts")

def isSettledTool(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isSettledTool``."""
    raise NotImplementedError("port isSettledTool from client/ui-conversation/src/client/contract/chat-nodes.ts")

class AssistantChatData(Protocol):
    """Surface stub for upstream interface ``AssistantChatData``."""
    pass

class ChatNodeDataMap(Protocol):
    """Surface stub for upstream interface ``ChatNodeDataMap``."""
    pass

class ManualCompactionChatData(Protocol):
    """Surface stub for upstream interface ``ManualCompactionChatData``."""
    pass

class RetryChatData(Protocol):
    """Surface stub for upstream interface ``RetryChatData``."""
    pass

class ToolChatData(Protocol):
    """Surface stub for upstream interface ``ToolChatData``."""
    pass

class TurnTailChatData(Protocol):
    """Surface stub for upstream interface ``TurnTailChatData``."""
    pass
