"""Auto-generated surface skeleton for upstream ``lsp/lsp-stdio/src/instance.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``lsp/lsp-stdio/src/instance.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "InstanceSpec",
    "LspInstance",
]

class LspInstance:
    """Surface stub for upstream class ``LspInstance``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LspInstance.__init__ from lsp/lsp-stdio/src/instance.ts")

class InstanceSpec(Protocol):
    """Surface stub for upstream interface ``InstanceSpec``."""
    pass
