"""Auto-generated surface skeleton for upstream ``llm/llm/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AdapterRegistrationHandle",
    "BlockAssembler",
    "DirectoryRegistrationHandle",
    "LlmAdapter",
    "LlmCallConfig",
    "LlmCallConfigAdapterDefaults",
    "LlmError",
    "LlmErrorOptions",
    "LlmRuntime",
    "PreparedLlmCall",
    "assertUsableApiKey",
    "callConfigEquals",
    "deepFreeze",
    "isAgentLoopRequest",
    "markAgentLoopRequest",
]

LlmCallConfig: TypeAlias = object  # port: surface stub

LlmCallConfigAdapterDefaults: TypeAlias = object  # port: surface stub

def assertUsableApiKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertUsableApiKey``."""
    raise NotImplementedError("port assertUsableApiKey from llm/llm/src/index.ts")

class LlmAdapter:
    """Surface stub for upstream class ``LlmAdapter``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LlmAdapter.__init__ from llm/llm/src/index.ts")

class LlmError:
    """Surface stub for upstream class ``LlmError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LlmError.__init__ from llm/llm/src/index.ts")

class LlmRuntime:
    """Surface stub for upstream class ``LlmRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LlmRuntime.__init__ from llm/llm/src/index.ts")

BlockAssembler = None  # port: surface stub (reexport)

callConfigEquals = None  # port: surface stub (reexport)

deepFreeze = None  # port: surface stub (reexport)

isAgentLoopRequest = None  # port: surface stub (reexport)

markAgentLoopRequest = None  # port: surface stub (reexport)

class AdapterRegistrationHandle(Protocol):
    """Surface stub for upstream interface ``AdapterRegistrationHandle``."""
    pass

class DirectoryRegistrationHandle(Protocol):
    """Surface stub for upstream interface ``DirectoryRegistrationHandle``."""
    pass

class LlmErrorOptions(Protocol):
    """Surface stub for upstream interface ``LlmErrorOptions``."""
    pass

class PreparedLlmCall(Protocol):
    """Surface stub for upstream interface ``PreparedLlmCall``."""
    pass
