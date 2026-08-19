"""Auto-generated surface skeleton for upstream ``client/ui-user-questions/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-user-questions/src/client/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "PendingQuestion",
    "PlanReview",
    "QuestionAnswer",
    "QuestionComposerProps",
    "QuestionKey",
    "QuestionWait",
    "apply",
    "inject",
]

PlanReview: TypeAlias = object  # port: surface stub

QuestionAnswer: TypeAlias = object  # port: surface stub

QuestionComposerProps: TypeAlias = object  # port: surface stub

QuestionKey: TypeAlias = object  # port: surface stub

QuestionWait: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/ui-user-questions/src/client/index.ts")

PendingQuestion = None  # port: surface stub (reexport)
