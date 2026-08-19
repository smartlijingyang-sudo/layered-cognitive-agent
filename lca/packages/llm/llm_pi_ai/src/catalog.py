"""Auto-generated surface skeleton for upstream ``llm/llm-pi-ai/src/catalog.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-pi-ai/src/catalog.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "MODALITIES",
    "SUPPORTED_THINKING_FORMATS",
    "THINKING_LEVELS",
    "PiAiCompatProfile",
    "PiAiModality",
    "PiAiModelOverride",
    "PiAiModelProfile",
    "PiAiReasoningEfforts",
    "PiAiThinkingFormat",
    "RouteCatalog",
    "RouteCatalogRequest",
    "catalogModels",
    "catalogProvider",
    "catalogProviderIds",
    "catalogProviderTakesApiKey",
    "resolveRouteModels",
]

PiAiModality: TypeAlias = object  # port: surface stub

PiAiModelOverride: TypeAlias = object  # port: surface stub

PiAiReasoningEfforts: TypeAlias = object  # port: surface stub

PiAiThinkingFormat: TypeAlias = object  # port: surface stub

MODALITIES = None  # port: surface stub

SUPPORTED_THINKING_FORMATS = None  # port: surface stub

THINKING_LEVELS = None  # port: surface stub

def catalogModels(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``catalogModels``."""
    raise NotImplementedError("port catalogModels from llm/llm-pi-ai/src/catalog.ts")

def catalogProvider(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``catalogProvider``."""
    raise NotImplementedError("port catalogProvider from llm/llm-pi-ai/src/catalog.ts")

def catalogProviderIds(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``catalogProviderIds``."""
    raise NotImplementedError("port catalogProviderIds from llm/llm-pi-ai/src/catalog.ts")

def catalogProviderTakesApiKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``catalogProviderTakesApiKey``."""
    raise NotImplementedError("port catalogProviderTakesApiKey from llm/llm-pi-ai/src/catalog.ts")

def resolveRouteModels(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveRouteModels``."""
    raise NotImplementedError("port resolveRouteModels from llm/llm-pi-ai/src/catalog.ts")

class PiAiCompatProfile(Protocol):
    """Surface stub for upstream interface ``PiAiCompatProfile``."""
    pass

class PiAiModelProfile(Protocol):
    """Surface stub for upstream interface ``PiAiModelProfile``."""
    pass

class RouteCatalog(Protocol):
    """Surface stub for upstream interface ``RouteCatalog``."""
    pass

class RouteCatalogRequest(Protocol):
    """Surface stub for upstream interface ``RouteCatalogRequest``."""
    pass
