"""Auto-generated surface skeleton for upstream ``code-runtime/code-runtime/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``code-runtime/code-runtime/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CodeBindingErrorClass",
    "CodeBindingFunction",
    "CodeBindingNamespace",
    "CodeJsonValue",
    "CodeRunFailure",
    "CodeRunRequest",
    "CodeRunResult",
]

CodeBindingFunction: TypeAlias = object  # port: surface stub

CodeJsonValue: TypeAlias = object  # port: surface stub

class CodeBindingErrorClass(Protocol):
    """Surface stub for upstream interface ``CodeBindingErrorClass``."""
    pass

class CodeBindingNamespace(Protocol):
    """Surface stub for upstream interface ``CodeBindingNamespace``."""
    pass

class CodeRunFailure(Protocol):
    """Surface stub for upstream interface ``CodeRunFailure``."""
    pass

class CodeRunRequest(Protocol):
    """Surface stub for upstream interface ``CodeRunRequest``."""
    pass

class CodeRunResult(Protocol):
    """Surface stub for upstream interface ``CodeRunResult``."""
    pass
