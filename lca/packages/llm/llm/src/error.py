"""Auto-generated surface skeleton for upstream ``llm/llm/src/error.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm/src/error.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CONTEXT_WINDOW_EXCEEDED_CODE",
    "EMPTY_RESPONSE_CODE",
    "HarnessError",
    "INVALID_CREDENTIAL_CODE",
    "QUOTA_EXCEEDED_CODE",
    "errorChain",
    "isContextWindowExceededError",
    "isHarnessError",
    "isQuotaExceededError",
]

CONTEXT_WINDOW_EXCEEDED_CODE = None  # port: surface stub

EMPTY_RESPONSE_CODE = None  # port: surface stub

INVALID_CREDENTIAL_CODE = None  # port: surface stub

QUOTA_EXCEEDED_CODE = None  # port: surface stub

def errorChain(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``errorChain``."""
    raise NotImplementedError("port errorChain from llm/llm/src/error.ts")

def isContextWindowExceededError(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isContextWindowExceededError``."""
    raise NotImplementedError("port isContextWindowExceededError from llm/llm/src/error.ts")

def isHarnessError(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isHarnessError``."""
    raise NotImplementedError("port isHarnessError from llm/llm/src/error.ts")

def isQuotaExceededError(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isQuotaExceededError``."""
    raise NotImplementedError("port isQuotaExceededError from llm/llm/src/error.ts")

class HarnessError:
    """Surface stub for upstream class ``HarnessError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port HarnessError.__init__ from llm/llm/src/error.ts")
