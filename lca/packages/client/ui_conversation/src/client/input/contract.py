"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/client/input/contract.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/client/input/contract.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ComposerKeyboard",
    "ConsumeTokenGuard",
    "DraftAttachmentId",
    "EditRange",
    "EditSelection",
    "InputActions",
    "InputEffect",
    "InputEvent",
    "InputMachineOptions",
    "InputNotice",
    "InputState",
    "InputTarget",
    "Occurrence",
    "PasteAttemptState",
    "PasteComponent",
    "QueuedMessage",
    "SessionInput",
    "SessionInputResolver",
    "SubmitAttempt",
]

ConsumeTokenGuard: TypeAlias = object  # port: surface stub

DraftAttachmentId: TypeAlias = object  # port: surface stub

InputEffect: TypeAlias = object  # port: surface stub

InputEvent: TypeAlias = object  # port: surface stub

QueuedMessage: TypeAlias = object  # port: surface stub

class ComposerKeyboard(Protocol):
    """Surface stub for upstream interface ``ComposerKeyboard``."""
    pass

class EditRange(Protocol):
    """Surface stub for upstream interface ``EditRange``."""
    pass

class EditSelection(Protocol):
    """Surface stub for upstream interface ``EditSelection``."""
    pass

class InputActions(Protocol):
    """Surface stub for upstream interface ``InputActions``."""
    pass

class InputMachineOptions(Protocol):
    """Surface stub for upstream interface ``InputMachineOptions``."""
    pass

class InputNotice(Protocol):
    """Surface stub for upstream interface ``InputNotice``."""
    pass

class InputState(Protocol):
    """Surface stub for upstream interface ``InputState``."""
    pass

class InputTarget(Protocol):
    """Surface stub for upstream interface ``InputTarget``."""
    pass

class Occurrence(Protocol):
    """Surface stub for upstream interface ``Occurrence``."""
    pass

class PasteAttemptState(Protocol):
    """Surface stub for upstream interface ``PasteAttemptState``."""
    pass

class PasteComponent(Protocol):
    """Surface stub for upstream interface ``PasteComponent``."""
    pass

class SessionInput(Protocol):
    """Surface stub for upstream interface ``SessionInput``."""
    pass

class SessionInputResolver(Protocol):
    """Surface stub for upstream interface ``SessionInputResolver``."""
    pass

class SubmitAttempt(Protocol):
    """Surface stub for upstream interface ``SubmitAttempt``."""
    pass
