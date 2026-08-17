"""Auto-generated surface skeleton for upstream ``client/ui-settings-plugins/src/client/card-form.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-settings-plugins/src/client/card-form.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CardActions",
    "CardFieldSpec",
    "CardFieldState",
    "CardForm",
    "CardSecretSpec",
    "CardShell",
    "FieldWrite",
    "numberField",
    "textField",
]

FieldWrite: TypeAlias = object  # port: surface stub

def numberField(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``numberField``."""
    raise NotImplementedError("port numberField from client/ui-settings-plugins/src/client/card-form.ts")

def textField(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``textField``."""
    raise NotImplementedError("port textField from client/ui-settings-plugins/src/client/card-form.ts")

class CardForm:
    """Surface stub for upstream class ``CardForm``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port CardForm.__init__ from client/ui-settings-plugins/src/client/card-form.ts")

class CardActions(Protocol):
    """Surface stub for upstream interface ``CardActions``."""
    pass

class CardFieldSpec(Protocol):
    """Surface stub for upstream interface ``CardFieldSpec``."""
    pass

class CardFieldState(Protocol):
    """Surface stub for upstream interface ``CardFieldState``."""
    pass

class CardSecretSpec(Protocol):
    """Surface stub for upstream interface ``CardSecretSpec``."""
    pass

class CardShell(Protocol):
    """Surface stub for upstream interface ``CardShell``."""
    pass
