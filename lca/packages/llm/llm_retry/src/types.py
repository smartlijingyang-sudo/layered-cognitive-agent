"""Auto-generated surface skeleton for upstream ``llm/llm-retry/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm-retry/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "LlmRetryEventData",
    "LlmRetryStartedEventData",
    "RetryId",
]

LlmRetryEventData: TypeAlias = object  # port: surface stub

RetryId: TypeAlias = object  # port: surface stub

class LlmRetryStartedEventData(Protocol):
    """Surface stub for upstream interface ``LlmRetryStartedEventData``."""
    pass
