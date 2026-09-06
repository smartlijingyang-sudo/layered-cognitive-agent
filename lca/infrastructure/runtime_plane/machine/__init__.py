"""Public exports for ``machine`` (auto-fixed)."""

from lca.infrastructure.runtime_plane.machine.machine import (
    resolve_machine,
    resolve_machine_transport,
    set_machine_resolver,
    set_machine_transport_resolver,
)

__all__ = ['set_machine_resolver', 'set_machine_transport_resolver', 'resolve_machine', 'resolve_machine_transport']
