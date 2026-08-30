"""Cost projection over journal LlmCallCompleted events (ADR-0065 PR-6).

Exposes:

- ``DefaultCostPricingTable`` — built-in pricing for common models.
- ``CostProjector`` — accumulates cost by model and pricing_ref.
"""

from lca.infrastructure.observability.cost.default_pricing import (
    DefaultCostPricingTable,
)
from lca.infrastructure.observability.cost.projector import CostProjector

__all__ = [
    "CostProjector",
    "DefaultCostPricingTable",
]
