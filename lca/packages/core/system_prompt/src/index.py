"""Auto-generated surface skeleton for upstream ``core/system-prompt/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/system-prompt/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "PERSONA_ORDER",
    "PERSONA_SECTION",
    "TOOL_ORDER_REST",
    "AssembleContext",
    "AssembledContext",
    "AssembledSection",
    "Config",
    "PromptAssembly",
    "PromptContext",
    "PromptSection",
    "SystemPrompt",
    "ToolProviderResult",
    "joinContextSections",
    "renderContextSections",
    "renderContextSnapshot",
    "renderPrompt",
]

PERSONA_ORDER = None  # port: surface stub

PERSONA_SECTION = None  # port: surface stub

TOOL_ORDER_REST = None  # port: surface stub

def joinContextSections(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``joinContextSections``."""
    raise NotImplementedError("port joinContextSections from core/system-prompt/src/index.ts")

def renderContextSections(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderContextSections``."""
    raise NotImplementedError("port renderContextSections from core/system-prompt/src/index.ts")

def renderContextSnapshot(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderContextSnapshot``."""
    raise NotImplementedError("port renderContextSnapshot from core/system-prompt/src/index.ts")

def renderPrompt(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderPrompt``."""
    raise NotImplementedError("port renderPrompt from core/system-prompt/src/index.ts")

class SystemPrompt:
    """Surface stub for upstream class ``SystemPrompt``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SystemPrompt.__init__ from core/system-prompt/src/index.ts")

class AssembleContext(Protocol):
    """Surface stub for upstream interface ``AssembleContext``."""
    pass

class AssembledContext(Protocol):
    """Surface stub for upstream interface ``AssembledContext``."""
    pass

class AssembledSection(Protocol):
    """Surface stub for upstream interface ``AssembledSection``."""
    pass

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class PromptAssembly(Protocol):
    """Surface stub for upstream interface ``PromptAssembly``."""
    pass

class PromptContext(Protocol):
    """Surface stub for upstream interface ``PromptContext``."""
    pass

class PromptSection(Protocol):
    """Surface stub for upstream interface ``PromptSection``."""
    pass

class ToolProviderResult(Protocol):
    """Surface stub for upstream interface ``ToolProviderResult``."""
    pass
