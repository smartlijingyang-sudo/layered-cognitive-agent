"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/context-provenance.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/context-provenance.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ContextProvenanceView",
    "ContextRole",
    "KnownContextForm",
    "contextForm",
    "contextProvenance",
]

ContextRole: TypeAlias = object  # port: surface stub

KnownContextForm: TypeAlias = object  # port: surface stub

def contextForm(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``contextForm``."""
    raise NotImplementedError("port contextForm from client/runtime/src/client/sessions/context-provenance.ts")

def contextProvenance(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``contextProvenance``."""
    raise NotImplementedError("port contextProvenance from client/runtime/src/client/sessions/context-provenance.ts")

class ContextProvenanceView(Protocol):
    """Surface stub for upstream interface ``ContextProvenanceView``."""
    pass
