"""Public exports for ``handler`` (auto-fixed)."""

from lca.infrastructure.handler.registry import (
    GenericInMemoryRegistry,
    UniqueOperationRegistry,
    make_inmemory_registry,
)

__all__ = ["GenericInMemoryRegistry", "UniqueOperationRegistry", "make_inmemory_registry"]
