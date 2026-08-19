"""Auto-generated surface skeleton for upstream ``interaction/user-questions/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``interaction/user-questions/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AskUserQuestionAnswer",
    "AskUserQuestionAnswerItem",
    "AskUserQuestionIntent",
    "AskUserQuestionItem",
    "AskUserQuestionOption",
]

AskUserQuestionIntent: TypeAlias = object  # port: surface stub

class AskUserQuestionAnswer(Protocol):
    """Surface stub for upstream interface ``AskUserQuestionAnswer``."""
    pass

class AskUserQuestionAnswerItem(Protocol):
    """Surface stub for upstream interface ``AskUserQuestionAnswerItem``."""
    pass

class AskUserQuestionItem(Protocol):
    """Surface stub for upstream interface ``AskUserQuestionItem``."""
    pass

class AskUserQuestionOption(Protocol):
    """Surface stub for upstream interface ``AskUserQuestionOption``."""
    pass
