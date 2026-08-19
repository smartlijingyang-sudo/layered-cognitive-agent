"""Auto-generated surface skeleton for upstream ``client/ui-primitives/src/ansi.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-primitives/src/ansi.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AnsiLine",
    "AnsiSpan",
    "parseAnsiLines",
]

AnsiLine: TypeAlias = object  # port: surface stub

def parseAnsiLines(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseAnsiLines``."""
    raise NotImplementedError("port parseAnsiLines from client/ui-primitives/src/ansi.ts")

class AnsiSpan(Protocol):
    """Surface stub for upstream interface ``AnsiSpan``."""
    pass
