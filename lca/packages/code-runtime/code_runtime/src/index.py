"""Auto-generated surface skeleton for upstream ``code-runtime/code-runtime/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``code-runtime/code-runtime/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "DUNDER_MEMBER",
    "PORTABLE_RESERVED_WORDS",
    "RESERVED_BINDING_GLOBALS",
    "RESERVED_ERROR_MEMBERS",
    "CodeBindingErrorClass",
    "CodeBindingFunction",
    "CodeBindingNamespace",
    "CodeJsonValue",
    "CodeRunFailure",
    "CodeRunRequest",
    "CodeRunResult",
    "CodeRuntime",
]

CodeBindingErrorClass: TypeAlias = object  # port: surface stub

CodeBindingFunction: TypeAlias = object  # port: surface stub

CodeBindingNamespace: TypeAlias = object  # port: surface stub

CodeJsonValue: TypeAlias = object  # port: surface stub

CodeRunFailure: TypeAlias = object  # port: surface stub

CodeRunRequest: TypeAlias = object  # port: surface stub

CodeRunResult: TypeAlias = object  # port: surface stub

DUNDER_MEMBER = None  # port: surface stub

PORTABLE_RESERVED_WORDS = None  # port: surface stub

RESERVED_BINDING_GLOBALS = None  # port: surface stub

RESERVED_ERROR_MEMBERS = None  # port: surface stub

class CodeRuntime:
    """Surface stub for upstream class ``CodeRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port CodeRuntime.__init__ from code-runtime/code-runtime/src/index.ts")
