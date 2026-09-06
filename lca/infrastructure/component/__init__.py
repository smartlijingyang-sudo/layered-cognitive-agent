"""Public exports for ``component`` (auto-fixed)."""

from lca.infrastructure.component.registry import (
    ComponentRegistry,
    NamedRegistry,
    RegistryKeyError,
)

__all__ = ['RegistryKeyError', 'NamedRegistry', 'ComponentRegistry']
