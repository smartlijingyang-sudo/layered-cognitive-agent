"""Public exports for ``scope`` (auto-fixed)."""

from lca.infrastructure.runtime_plane.scope.scope import (
    plane_bindings_scope,
    current_bindings,
    current_primary,
    resolve_plane_path,
    path_needs_approval,
    raise_if_out_of_scope,
)

__all__ = ['plane_bindings_scope', 'current_bindings', 'current_primary', 'resolve_plane_path', 'path_needs_approval', 'raise_if_out_of_scope']
