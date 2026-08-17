"""Auto-generated surface skeleton for upstream ``llm/llm-deepseek/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-deepseek/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "DEFAULT_CONTEXT_WINDOW",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_STREAM_IDLE_TIMEOUT_MS",
    "DeepSeekAdapter",
    "DeepSeekAdapterOptions",
    "DeepSeekCatalogModel",
    "DeepSeekConnectionOptions",
    "PUBLIC_BASE_URL",
    "RequestDefaults",
    "ResolvedDeepSeekOptions",
    "apply",
    "inject",
    "name",
    "resolveAdapterOptions",
]

DeepSeekAdapterOptions: TypeAlias = object  # port: surface stub

DeepSeekCatalogModel: TypeAlias = object  # port: surface stub

DeepSeekConnectionOptions: TypeAlias = object  # port: surface stub

RequestDefaults: TypeAlias = object  # port: surface stub

ResolvedDeepSeekOptions: TypeAlias = object  # port: surface stub

PUBLIC_BASE_URL = None  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from llm/llm-deepseek/src/index.ts")

def resolveAdapterOptions(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveAdapterOptions``."""
    raise NotImplementedError("port resolveAdapterOptions from llm/llm-deepseek/src/index.ts")

DEFAULT_CONTEXT_WINDOW = None  # port: surface stub (reexport)

DEFAULT_MAX_TOKENS = None  # port: surface stub (reexport)

DEFAULT_STREAM_IDLE_TIMEOUT_MS = None  # port: surface stub (reexport)

DeepSeekAdapter = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
