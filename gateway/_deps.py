"""Shared dependency accessors — breaks the app ↔ openai_compat_api import cycle.

Both ``gateway.app`` and ``gateway.openai_compat_api`` need access to the
``RunRegistry`` and ``FileStore`` singletons.  Previously ``openai_compat_api``
used a lazy ``from gateway.app import ...`` to avoid the cycle; this module
provides a proper indirection point instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gateway.run_registry import RunRegistry
    from lca.layer0_infra.file_store import LocalFileStore

_registry: RunRegistry | None = None
_file_store: LocalFileStore | None = None


def set_deps(*, registry: RunRegistry, file_store: LocalFileStore) -> None:
    """Called once by ``create_app()`` to wire shared dependencies."""
    global _registry, _file_store
    _registry = registry
    _file_store = file_store


def get_registry() -> RunRegistry:
    if _registry is None:
        msg = "gateway deps not initialized (call create_app first)"
        raise RuntimeError(msg)
    return _registry


def get_file_store() -> LocalFileStore:
    if _file_store is None:
        msg = "gateway deps not initialized (call create_app first)"
        raise RuntimeError(msg)
    return _file_store
