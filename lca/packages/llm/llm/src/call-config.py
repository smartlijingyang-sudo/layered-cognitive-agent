"""Auto-generated surface skeleton for upstream ``llm/llm/src/call-config.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm/src/call-config.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "LlmCallConfig",
    "LlmCallConfigAdapterDefaults",
    "callConfigEquals",
    "deepFreeze",
    "isAgentLoopRequest",
    "markAgentLoopRequest",
]

def callConfigEquals(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``callConfigEquals``."""
    raise NotImplementedError("port callConfigEquals from llm/llm/src/call-config.ts")

def deepFreeze(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deepFreeze``."""
    raise NotImplementedError("port deepFreeze from llm/llm/src/call-config.ts")

def isAgentLoopRequest(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isAgentLoopRequest``."""
    raise NotImplementedError("port isAgentLoopRequest from llm/llm/src/call-config.ts")

def markAgentLoopRequest(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``markAgentLoopRequest``."""
    raise NotImplementedError("port markAgentLoopRequest from llm/llm/src/call-config.ts")

class LlmCallConfig(Protocol):
    """Surface stub for upstream interface ``LlmCallConfig``."""
    pass

class LlmCallConfigAdapterDefaults(Protocol):
    """Surface stub for upstream interface ``LlmCallConfigAdapterDefaults``."""
    pass
