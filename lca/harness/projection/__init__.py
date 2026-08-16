"""Projection registry and first-party web projections."""

from lca.harness.projection.registry import InMemoryProjectionRegistry
from lca.harness.projection.web import ActivityProjection, ConversationProjection

__all__ = [
    "ActivityProjection",
    "ConversationProjection",
    "InMemoryProjectionRegistry",
]
