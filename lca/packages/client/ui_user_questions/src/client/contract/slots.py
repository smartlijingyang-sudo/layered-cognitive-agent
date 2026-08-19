"""Auto-generated surface skeleton for upstream ``client/ui-user-questions/src/client/contract/slots.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-user-questions/src/client/contract/slots.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PendingQuestion",
    "PlanReview",
    "QuestionAnswer",
    "QuestionComposerProps",
    "QuestionWait",
    "planReviewOf",
]

QuestionAnswer: TypeAlias = object  # port: surface stub

QuestionComposerProps: TypeAlias = object  # port: surface stub

QuestionWait: TypeAlias = object  # port: surface stub

def planReviewOf(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``planReviewOf``."""
    raise NotImplementedError("port planReviewOf from client/ui-user-questions/src/client/contract/slots.ts")

class PendingQuestion:
    """Surface stub for upstream class ``PendingQuestion``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PendingQuestion.__init__ from client/ui-user-questions/src/client/contract/slots.ts")

class PlanReview(Protocol):
    """Surface stub for upstream interface ``PlanReview``."""
    pass
