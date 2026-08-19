"""Auto-generated surface skeleton for upstream ``llm/llm-deepseek/src/adapter.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-deepseek/src/adapter.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "DEFAULT_CONTEXT_WINDOW",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_STREAM_IDLE_TIMEOUT_MS",
    "DeepSeekAdapter",
    "DeepSeekAdapterOptions",
    "DeepSeekCatalogModel",
    "DeepSeekConnectionOptions",
    "httpErrorCode",
]

DEFAULT_CONTEXT_WINDOW = None  # port: surface stub

DEFAULT_MAX_TOKENS = None  # port: surface stub

DEFAULT_STREAM_IDLE_TIMEOUT_MS = None  # port: surface stub

def httpErrorCode(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``httpErrorCode``."""
    raise NotImplementedError("port httpErrorCode from llm/llm-deepseek/src/adapter.ts")

class DeepSeekAdapter:
    """Surface stub for upstream class ``DeepSeekAdapter``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DeepSeekAdapter.__init__ from llm/llm-deepseek/src/adapter.ts")

class DeepSeekAdapterOptions(Protocol):
    """Surface stub for upstream interface ``DeepSeekAdapterOptions``."""
    pass

class DeepSeekCatalogModel(Protocol):
    """Surface stub for upstream interface ``DeepSeekCatalogModel``."""
    pass

class DeepSeekConnectionOptions(Protocol):
    """Surface stub for upstream interface ``DeepSeekConnectionOptions``."""
    pass
