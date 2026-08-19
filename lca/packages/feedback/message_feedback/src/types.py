"""Auto-generated surface skeleton for upstream ``feedback/message-feedback/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``feedback/message-feedback/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "MessageFeedbackDeleteRequest",
    "MessageFeedbackDeleteResult",
    "MessageFeedbackDeleteValue",
    "MessageFeedbackFailure",
    "MessageFeedbackItem",
    "MessageFeedbackListRequest",
    "MessageFeedbackListResult",
    "MessageFeedbackListValue",
    "MessageFeedbackNoteBlank",
    "MessageFeedbackNoteTooLarge",
    "MessageFeedbackPutRequest",
    "MessageFeedbackPutResult",
    "MessageFeedbackRating",
    "MessageFeedbackRejected",
    "MessageFeedbackSessionNotFound",
    "MessageFeedbackSuccess",
    "MessageFeedbackTargetNotFound",
    "MessageFeedbackVersion",
    "MessageFeedbackVersionConflict",
]

MessageFeedbackDeleteResult: TypeAlias = object  # port: surface stub

MessageFeedbackFailure: TypeAlias = object  # port: surface stub

MessageFeedbackListResult: TypeAlias = object  # port: surface stub

MessageFeedbackPutResult: TypeAlias = object  # port: surface stub

MessageFeedbackRating: TypeAlias = object  # port: surface stub

MessageFeedbackVersion: TypeAlias = object  # port: surface stub

class MessageFeedbackDeleteRequest(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackDeleteRequest``."""
    pass

class MessageFeedbackDeleteValue(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackDeleteValue``."""
    pass

class MessageFeedbackItem(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackItem``."""
    pass

class MessageFeedbackListRequest(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackListRequest``."""
    pass

class MessageFeedbackListValue(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackListValue``."""
    pass

class MessageFeedbackNoteBlank(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackNoteBlank``."""
    pass

class MessageFeedbackNoteTooLarge(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackNoteTooLarge``."""
    pass

class MessageFeedbackPutRequest(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackPutRequest``."""
    pass

class MessageFeedbackRejected(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackRejected``."""
    pass

class MessageFeedbackSessionNotFound(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackSessionNotFound``."""
    pass

class MessageFeedbackSuccess(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackSuccess``."""
    pass

class MessageFeedbackTargetNotFound(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackTargetNotFound``."""
    pass

class MessageFeedbackVersionConflict(Protocol):
    """Surface stub for upstream interface ``MessageFeedbackVersionConflict``."""
    pass
