"""Auto-generated surface skeleton for upstream ``core/tools/src/code-mode.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/tools/src/code-mode.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "RUN_CODE_NAME",
    "SDK_SECTION_ORDER",
    "CodeRunFailedError",
    "CodeSdkLanguage",
    "RunCodeBridgeOptions",
    "createRunCodeTool",
]

CodeSdkLanguage: TypeAlias = object  # port: surface stub

RUN_CODE_NAME = None  # port: surface stub

SDK_SECTION_ORDER = None  # port: surface stub

def createRunCodeTool(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createRunCodeTool``."""
    raise NotImplementedError("port createRunCodeTool from core/tools/src/code-mode.ts")

class CodeRunFailedError:
    """Surface stub for upstream class ``CodeRunFailedError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port CodeRunFailedError.__init__ from core/tools/src/code-mode.ts")

class RunCodeBridgeOptions(Protocol):
    """Surface stub for upstream interface ``RunCodeBridgeOptions``."""
    pass
