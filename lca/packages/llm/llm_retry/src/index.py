"""Auto-generated surface skeleton for upstream ``llm/llm-retry/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-retry/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "LlmRetryEventData",
    "LlmRetryStartedEventData",
    "RetryId",
    "RetryInternals",
    "apply",
    "inject",
    "name",
]

Config: TypeAlias = object  # port: surface stub

LlmRetryEventData: TypeAlias = object  # port: surface stub

LlmRetryStartedEventData: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from llm/llm-retry/src/index.ts")

RetryId = None  # port: surface stub (reexport)

class RetryInternals(Protocol):
    """Surface stub for upstream interface ``RetryInternals``."""
    pass
