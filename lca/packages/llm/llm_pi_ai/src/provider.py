"""Auto-generated surface skeleton for upstream ``llm/llm-pi-ai/src/provider.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-pi-ai/src/provider.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "ProviderSpec",
    "buildProvider",
    "supportedProtocols",
]

def buildProvider(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``buildProvider``."""
    raise NotImplementedError("port buildProvider from llm/llm-pi-ai/src/provider.ts")

def supportedProtocols(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``supportedProtocols``."""
    raise NotImplementedError("port supportedProtocols from llm/llm-pi-ai/src/provider.ts")

class ProviderSpec(Protocol):
    """Surface stub for upstream interface ``ProviderSpec``."""
    pass
