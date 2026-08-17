"""Scope primitives and layered registries (DSH ``core/scope`` mirror)."""

from __future__ import annotations

from lca.layer0_infra.plugin.scope.index import (
    ScopeCarrier,
    ScopeKey,
    bind_scope_parent,
    create_scope,
    scope_chain_of,
    scope_of,
    scope_parent_of,
    scope_target,
)
from lca.layer0_infra.plugin.scope.store import (
    AnonymousEntries,
    NamedEntries,
    ScopedLayers,
    ScopeLayer,
)

__all__ = [
    "AnonymousEntries",
    "NamedEntries",
    "ScopeCarrier",
    "ScopeKey",
    "ScopeLayer",
    "ScopedLayers",
    "bind_scope_parent",
    "create_scope",
    "scope_chain_of",
    "scope_of",
    "scope_parent_of",
    "scope_target",
]
