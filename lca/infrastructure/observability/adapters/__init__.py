"""observability.adapters — LLM boundary observability (Session SSOT only).

LLM call boundaries emit ``llm.call.start`` / ``llm.call.end`` /
``llm.stream.token`` / ``llm.stream.stall`` via :class:`LlmSpineEmitter`,
which routes through :func:`Session.append` per ADR-0186 / ADR-0192.

The legacy ``TelemetryMemoryAdapter`` dual-write to ``MemoryJournal``
(``facade.record`` / ``facade.span``) had no readers outside descriptors
and tests; it is removed (delete-when met).
"""

from lca.infrastructure.observability.adapters.adapters import (
    TelemetryLLMAdapter,
)

__all__ = ["TelemetryLLMAdapter"]
