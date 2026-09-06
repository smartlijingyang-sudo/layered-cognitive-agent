"""Public exports for ``scope`` (auto-fixed)."""

from lca.infrastructure.runtime_plane.scope.scope import (
    current_bindings,
    current_primary,
    path_needs_approval,
    plane_bindings_scope,
    raise_if_out_of_scope,
    resolve_plane_path,
)

__all__ = ['plane_bindings_scope', 'current_bindings', 'current_primary', 'resolve_plane_path', 'path_needs_approval', 'raise_if_out_of_scope']
