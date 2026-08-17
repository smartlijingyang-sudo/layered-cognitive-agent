"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/conversation-assembler.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/conversation-assembler.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ConversationEventDefinitions",
    "ConversationNodeAssembler",
    "ConversationRuntime",
    "ConversationViewDefinitions",
]

class ConversationNodeAssembler:
    """Surface stub for upstream class ``ConversationNodeAssembler``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ConversationNodeAssembler.__init__ from client/runtime/src/client/sessions/conversation-assembler.ts")

class ConversationEventDefinitions(Protocol):
    """Surface stub for upstream interface ``ConversationEventDefinitions``."""
    pass

class ConversationRuntime(Protocol):
    """Surface stub for upstream interface ``ConversationRuntime``."""
    pass

class ConversationViewDefinitions(Protocol):
    """Surface stub for upstream interface ``ConversationViewDefinitions``."""
    pass
