"""Auto-generated surface skeleton for upstream ``client/ui-commands/src/client/contract.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-commands/src/client/contract.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CommandContribution",
    "CommandDecoration",
    "CommandUiContract",
    "CommandUiSpec",
    "SelectConfirmation",
    "SelectOption",
]

CommandUiSpec: TypeAlias = object  # port: surface stub

class CommandContribution(Protocol):
    """Surface stub for upstream interface ``CommandContribution``."""
    pass

class CommandDecoration(Protocol):
    """Surface stub for upstream interface ``CommandDecoration``."""
    pass

class CommandUiContract(Protocol):
    """Surface stub for upstream interface ``CommandUiContract``."""
    pass

class SelectConfirmation(Protocol):
    """Surface stub for upstream interface ``SelectConfirmation``."""
    pass

class SelectOption(Protocol):
    """Surface stub for upstream interface ``SelectOption``."""
    pass
