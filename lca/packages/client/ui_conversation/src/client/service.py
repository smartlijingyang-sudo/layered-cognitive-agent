"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/client/service.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/client/service.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "ConversationController",
    "IConversation",
    "UnsupportedImageMediaTypeError",
]

class ConversationController:
    """Surface stub for upstream class ``ConversationController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ConversationController.__init__ from client/ui-conversation/src/client/service.ts")

class UnsupportedImageMediaTypeError:
    """Surface stub for upstream class ``UnsupportedImageMediaTypeError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port UnsupportedImageMediaTypeError.__init__ from client/ui-conversation/src/client/service.ts")

class IConversation(Protocol):
    """Surface stub for upstream interface ``IConversation``."""
    pass
