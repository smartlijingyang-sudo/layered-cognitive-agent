"""Auto-generated surface skeleton for upstream ``lsp/lsp-stdio/src/framing.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``lsp/lsp-stdio/src/framing.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "MessageDecoder",
    "encodeMessage",
]

def encodeMessage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``encodeMessage``."""
    raise NotImplementedError("port encodeMessage from lsp/lsp-stdio/src/framing.ts")

class MessageDecoder:
    """Surface stub for upstream class ``MessageDecoder``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port MessageDecoder.__init__ from lsp/lsp-stdio/src/framing.ts")
