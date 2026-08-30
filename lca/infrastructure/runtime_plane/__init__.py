"""Product-environment binding — resolve, scope, path audit."""

from lca.contracts.models.core.plane import PlaneBindings, PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.paths import join_under, outputs_under
from lca.infrastructure.runtime_plane.resolve import (
    PlaneBindingError,
    PlaneRequest,
    make_sandbox_ref,
    ref_of,
    resolve_plane_bindings,
    sandbox_ref_from,
)
from lca.infrastructure.runtime_plane.scope import (
    current_bindings,
    current_primary,
    path_needs_approval,
    plane_bindings_scope,
    raise_if_out_of_scope,
    resolve_plane_path,
)

__all__ = [
    "PlaneBindingError",
    "PlaneBindings",
    "PlaneKind",
    "PlaneRef",
    "PlaneRequest",
    "current_bindings",
    "current_primary",
    "join_under",
    "make_sandbox_ref",
    "outputs_under",
    "path_needs_approval",
    "plane_bindings_scope",
    "raise_if_out_of_scope",
    "ref_of",
    "resolve_plane_bindings",
    "resolve_plane_path",
    "sandbox_ref_from",
]
