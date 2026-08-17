"""Auto-generated surface skeleton for upstream ``interaction/user-questions/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``interaction/user-questions/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AskUserQuestionAnswer",
    "AskUserQuestionAnswerItem",
    "AskUserQuestionIntent",
    "AskUserQuestionItem",
    "AskUserQuestionOption",
    "AskUserQuestionRequest",
    "UserQuestionError",
    "UserQuestionProvider",
    "UserQuestionService",
]

AskUserQuestionAnswer: TypeAlias = object  # port: surface stub

AskUserQuestionAnswerItem: TypeAlias = object  # port: surface stub

AskUserQuestionIntent: TypeAlias = object  # port: surface stub

AskUserQuestionItem: TypeAlias = object  # port: surface stub

AskUserQuestionOption: TypeAlias = object  # port: surface stub

class UserQuestionError:
    """Surface stub for upstream class ``UserQuestionError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port UserQuestionError.__init__ from interaction/user-questions/src/index.ts")

class UserQuestionService:
    """Surface stub for upstream class ``UserQuestionService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port UserQuestionService.__init__ from interaction/user-questions/src/index.ts")

class AskUserQuestionRequest(Protocol):
    """Surface stub for upstream interface ``AskUserQuestionRequest``."""
    pass

class UserQuestionProvider(Protocol):
    """Surface stub for upstream interface ``UserQuestionProvider``."""
    pass
