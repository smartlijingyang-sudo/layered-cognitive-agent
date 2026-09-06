"""Session fold public API (ADR-0195 P4-S03)."""

from __future__ import annotations

from lca_kernel.events.fold.fold import (
    REQUEST_HEADER_CATEGORY,
    SURFACE_ASSISTANT_TYPE,
    SURFACE_TOOL_RESULT_TYPE,
    canonicalHeader,
    foldRequestHeader,
    foldSurface,
    headerEquals,
)

__all__ = [
    "REQUEST_HEADER_CATEGORY",
    "SURFACE_ASSISTANT_TYPE",
    "SURFACE_TOOL_RESULT_TYPE",
    "canonicalHeader",
    "foldRequestHeader",
    "foldSurface",
    "headerEquals",
]
