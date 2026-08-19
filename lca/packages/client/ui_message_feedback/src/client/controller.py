"""Auto-generated surface skeleton for upstream ``client/ui-message-feedback/src/client/controller.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-message-feedback/src/client/controller.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "MessageFeedbackActionResult",
    "MessageFeedbackController",
    "MessageFeedbackRemote",
    "MessageFeedbackStatus",
    "MessageFeedbackView",
]

MessageFeedbackActionResult: TypeAlias = object  # port: surface stub

MessageFeedbackStatus: TypeAlias = object  # port: surface stub

class MessageFeedbackController:
    """Surface stub for upstream class ``MessageFeedbackController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port MessageFeedbackController.__init__ from client/ui-message-feedback/src/client/controller.ts")

class MessageFeedbackRemote(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackRemote``."""
    pass

class MessageFeedbackView(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackView``."""
    pass
