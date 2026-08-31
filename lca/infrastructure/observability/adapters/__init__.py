"""observability.adapters — adapter subpackage."""

from lca.infrastructure.observability.adapters.memory_adapter import (
    TelemetryMemoryAdapter,
)

__all__ = ["TelemetryMemoryAdapter"]
