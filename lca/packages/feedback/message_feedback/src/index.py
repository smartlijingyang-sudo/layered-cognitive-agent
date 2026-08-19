"""Auto-generated surface skeleton for upstream ``feedback/message-feedback/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``feedback/message-feedback/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "MessageFeedbackRow",
    "MessageFeedbackService",
    "MessageFeedbackSessionIdentity",
    "messageFeedbackDomainSpec",
    "messageFeedbackItemSchema",
    "messageFeedbackRatingSchema",
    "messageFeedbackRowSchema",
    "messageFeedbackSessionIdentitySchema",
    "messageFeedbackVersionSchema",
]

MessageFeedbackRow: TypeAlias = object  # port: surface stub

MessageFeedbackSessionIdentity: TypeAlias = object  # port: surface stub

class MessageFeedbackService:
    """Surface stub for upstream class ``MessageFeedbackService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port MessageFeedbackService.__init__ from feedback/message-feedback/src/index.ts")

messageFeedbackDomainSpec = None  # port: surface stub (reexport)

messageFeedbackItemSchema = None  # port: surface stub (reexport)

messageFeedbackRatingSchema = None  # port: surface stub (reexport)

messageFeedbackRowSchema = None  # port: surface stub (reexport)

messageFeedbackSessionIdentitySchema = None  # port: surface stub (reexport)

messageFeedbackVersionSchema = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
