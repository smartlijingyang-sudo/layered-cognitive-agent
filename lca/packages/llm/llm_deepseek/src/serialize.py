"""Auto-generated surface skeleton for upstream ``llm/llm-deepseek/src/serialize.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-deepseek/src/serialize.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "RequestDefaults",
    "serializeMessages",
    "serializeRequest",
]

def serializeMessages(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``serializeMessages``."""
    raise NotImplementedError("port serializeMessages from llm/llm-deepseek/src/serialize.ts")

def serializeRequest(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``serializeRequest``."""
    raise NotImplementedError("port serializeRequest from llm/llm-deepseek/src/serialize.ts")

class RequestDefaults(Protocol):
    """Surface stub for upstream interface ``RequestDefaults``."""
    pass
