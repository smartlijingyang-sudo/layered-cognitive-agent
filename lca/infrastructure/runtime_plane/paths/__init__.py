"""Public exports for ``paths`` — kind-agnostic path algebra."""

from lca.infrastructure.runtime_plane.paths.paths import (
    is_absolute,
    is_temp_path,
    is_windows,
    is_within,
    join_under,
    normalize,
    outputs_under,
    resolve_plane_path,
    within_any,
)

__all__ = [
    "is_absolute",
    "is_temp_path",
    "is_windows",
    "is_within",
    "join_under",
    "normalize",
    "outputs_under",
    "resolve_plane_path",
    "within_any",
]
