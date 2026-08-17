"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/client/contract/slots.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/client/contract/slots.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ApprovalComposerProps",
    "ApprovalWait",
    "AssistantActionOwnerProps",
    "ChatFileMentions",
    "ChatNodeOwnerProps",
    "ChatNodeTurnDataInjected",
    "ChatNodeViewProps",
    "ChatScrollPosition",
    "ChatStore",
    "ChatViewInjected",
    "ChatViewSlotProps",
    "CommandRowOwnerProps",
    "CommandRowProps",
    "ComposerAttachment",
    "ComposerBarInjected",
    "ComposerBarOwnerProps",
    "ComposerBarProps",
    "ComposerChainProps",
    "ConvViewOwnerProps",
    "ConvViewProps",
    "ConversationHeaderActionOwnerProps",
    "ConversationInjected",
    "ConversationSessionHeaderInjected",
    "ConversationSessionHeaderSlotProps",
    "ConversationSessionInjected",
    "ConversationSessionOwnerProps",
    "ConversationSessionSlotProps",
    "ConversationSlotProps",
    "DetailsInjected",
    "DetailsSlotProps",
    "DetailsToolOwnerProps",
    "EmptyWorkspaceOwnerProps",
    "HeroAgentPresetOwnerProps",
    "InputControlOwnerProps",
    "InputZone",
    "PendingApproval",
    "TurnTailOwnerProps",
    "UseChatNodeTurnData",
]

ApprovalComposerProps: TypeAlias = object  # port: surface stub

ApprovalWait: TypeAlias = object  # port: surface stub

ChatNodeViewProps: TypeAlias = object  # port: surface stub

ChatStore: TypeAlias = object  # port: surface stub

ChatViewSlotProps: TypeAlias = object  # port: surface stub

CommandRowProps: TypeAlias = object  # port: surface stub

ComposerBarProps: TypeAlias = object  # port: surface stub

ConvViewProps: TypeAlias = object  # port: surface stub

ConversationSessionHeaderSlotProps: TypeAlias = object  # port: surface stub

ConversationSessionSlotProps: TypeAlias = object  # port: surface stub

ConversationSlotProps: TypeAlias = object  # port: surface stub

DetailsSlotProps: TypeAlias = object  # port: surface stub

UseChatNodeTurnData: TypeAlias = object  # port: surface stub

class PendingApproval:
    """Surface stub for upstream class ``PendingApproval``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PendingApproval.__init__ from client/ui-conversation/src/client/contract/slots.ts")

class AssistantActionOwnerProps(Protocol):
    """Surface stub for upstream interface ``AssistantActionOwnerProps``."""
    pass

class ChatFileMentions(Protocol):
    """Surface stub for upstream interface ``ChatFileMentions``."""
    pass

class ChatNodeOwnerProps(Protocol):
    """Surface stub for upstream interface ``ChatNodeOwnerProps``."""
    pass

class ChatNodeTurnDataInjected(Protocol):
    """Surface stub for upstream interface ``ChatNodeTurnDataInjected``."""
    pass

class ChatScrollPosition(Protocol):
    """Surface stub for upstream interface ``ChatScrollPosition``."""
    pass

class ChatViewInjected(Protocol):
    """Surface stub for upstream interface ``ChatViewInjected``."""
    pass

class CommandRowOwnerProps(Protocol):
    """Surface stub for upstream interface ``CommandRowOwnerProps``."""
    pass

class ComposerAttachment(Protocol):
    """Surface stub for upstream interface ``ComposerAttachment``."""
    pass

class ComposerBarInjected(Protocol):
    """Surface stub for upstream interface ``ComposerBarInjected``."""
    pass

class ComposerBarOwnerProps(Protocol):
    """Surface stub for upstream interface ``ComposerBarOwnerProps``."""
    pass

class ComposerChainProps(Protocol):
    """Surface stub for upstream interface ``ComposerChainProps``."""
    pass

class ConvViewOwnerProps(Protocol):
    """Surface stub for upstream interface ``ConvViewOwnerProps``."""
    pass

class ConversationHeaderActionOwnerProps(Protocol):
    """Surface stub for upstream interface ``ConversationHeaderActionOwnerProps``."""
    pass

class ConversationInjected(Protocol):
    """Surface stub for upstream interface ``ConversationInjected``."""
    pass

class ConversationSessionHeaderInjected(Protocol):
    """Surface stub for upstream interface ``ConversationSessionHeaderInjected``."""
    pass

class ConversationSessionInjected(Protocol):
    """Surface stub for upstream interface ``ConversationSessionInjected``."""
    pass

class ConversationSessionOwnerProps(Protocol):
    """Surface stub for upstream interface ``ConversationSessionOwnerProps``."""
    pass

class DetailsInjected(Protocol):
    """Surface stub for upstream interface ``DetailsInjected``."""
    pass

class DetailsToolOwnerProps(Protocol):
    """Surface stub for upstream interface ``DetailsToolOwnerProps``."""
    pass

class EmptyWorkspaceOwnerProps(Protocol):
    """Surface stub for upstream interface ``EmptyWorkspaceOwnerProps``."""
    pass

class HeroAgentPresetOwnerProps(Protocol):
    """Surface stub for upstream interface ``HeroAgentPresetOwnerProps``."""
    pass

class InputControlOwnerProps(Protocol):
    """Surface stub for upstream interface ``InputControlOwnerProps``."""
    pass

class InputZone(Protocol):
    """Surface stub for upstream interface ``InputZone``."""
    pass

class TurnTailOwnerProps(Protocol):
    """Surface stub for upstream interface ``TurnTailOwnerProps``."""
    pass
