"""Auto-generated surface skeleton for upstream ``llm/llm-deepseek/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-deepseek/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "WireAssistantMessage",
    "WireChoice",
    "WireChunk",
    "WireDelta",
    "WireError",
    "WireMessage",
    "WireRequest",
    "WireSystemMessage",
    "WireTool",
    "WireToolCall",
    "WireToolCallDelta",
    "WireToolMessage",
    "WireUsage",
    "WireUserMessage",
]

WireMessage: TypeAlias = object  # port: surface stub

class WireAssistantMessage(Protocol):
    """Surface stub for upstream interface ``WireAssistantMessage``."""
    pass

class WireChoice(Protocol):
    """Surface stub for upstream interface ``WireChoice``."""
    pass

class WireChunk(Protocol):
    """Surface stub for upstream interface ``WireChunk``."""
    pass

class WireDelta(Protocol):
    """Surface stub for upstream interface ``WireDelta``."""
    pass

class WireError(Protocol):
    """Surface stub for upstream interface ``WireError``."""
    pass

class WireRequest(Protocol):
    """Surface stub for upstream interface ``WireRequest``."""
    pass

class WireSystemMessage(Protocol):
    """Surface stub for upstream interface ``WireSystemMessage``."""
    pass

class WireTool(Protocol):
    """Surface stub for upstream interface ``WireTool``."""
    pass

class WireToolCall(Protocol):
    """Surface stub for upstream interface ``WireToolCall``."""
    pass

class WireToolCallDelta(Protocol):
    """Surface stub for upstream interface ``WireToolCallDelta``."""
    pass

class WireToolMessage(Protocol):
    """Surface stub for upstream interface ``WireToolMessage``."""
    pass

class WireUsage(Protocol):
    """Surface stub for upstream interface ``WireUsage``."""
    pass

class WireUserMessage(Protocol):
    """Surface stub for upstream interface ``WireUserMessage``."""
    pass
