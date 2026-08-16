"""ScopedPluginHost — PluginHost with parent delegation + ContextVar propagation.

This is the harness-level extension of ``PluginHost`` that adds three capabilities:

1. **Parent delegation**: ``resolve()`` checks self first, then walks up the parent chain.
2. **Scope forking**: ``fork()`` creates a child scope with its own service table.
3. **Async propagation**: ``run_in_scope()`` sets a ``ContextVar`` so any code in the
   async task tree can access the current scope via ``ScopedPluginHost.current()``.

``PluginHost`` is equivalent to ``ScopedPluginHost(parent=None)``. The existing
plugin kernel is not modified — ``ScopedPluginHost`` composes a ``PluginHost``
internally and delegates service table operations to it.

Spec reference: §3.1 of ``docs/specs/harness-spine-spec.md``.
"""

from __future__ import annotations

import contextlib
import contextvars
from typing import Any

from lca.contracts.harness.plugin import ScopeKind
from lca.layer0_infra.plugin.kernel._host import PluginHost

_current_scope: contextvars.ContextVar[ScopedPluginHost | None] = contextvars.ContextVar(
    "plugin_scope", default=None
)


class ServiceNotFoundError(KeyError):
    """Raised when ``resolve()`` cannot find a service in any scope."""


class ScopedPluginHost:
    """Plugin host with hierarchical scope delegation.

    Each scope has its own ``PluginHost`` (service table + event bus + handles).
    Resolution walks up the parent chain: nearest scope wins.

    Constraints:
    - Child scopes can shadow allowlisted services from parent.
    - Child cannot publish to parent.
    - Parent unload requires all children to drain first.
    """

    def __init__(
        self,
        parent: ScopedPluginHost | None,
        scope_kind: ScopeKind,
        scope_id: str,
    ) -> None:
        self._parent = parent
        self._kind = scope_kind
        self._id = scope_id
        self._host = PluginHost()
        self._children: list[ScopedPluginHost] = []

    # ── Properties ────────────────────────────────────────

    @property
    def scope_kind(self) -> ScopeKind:
        return self._kind

    @property
    def scope_id(self) -> str:
        return self._id

    @property
    def parent(self) -> ScopedPluginHost | None:
        return self._parent

    @property
    def host(self) -> PluginHost:
        """Direct access to the underlying ``PluginHost`` for kernel operations."""
        return self._host

    @property
    def children(self) -> list[ScopedPluginHost]:
        return list(self._children)

    # ── Service resolution (parent delegation) ────────────

    def resolve(self, service_key: str) -> Any:
        """Resolve a service by walking up the scope chain.

        Checks self first, then parent, grandparent, etc.
        Raises ``ServiceNotFound`` if no scope in the chain provides it.
        """
        record = self._host.get_service_record(service_key)
        if record is not None and record.available:
            return record.value
        if self._parent is not None:
            return self._parent.resolve(service_key)
        raise ServiceNotFoundError(service_key)

    def get(self, service_key: str, default: Any = None) -> Any:
        """Non-raising variant of ``resolve()``."""
        try:
            return self.resolve(service_key)
        except ServiceNotFoundError:
            return default

    def provide(self, handle: Any, name: str, value: Any, check: Any = None) -> None:
        """Mount a service in THIS scope (does not propagate to parent)."""
        self._host.provide(handle, name, value, check)

    # ── Scope forking ─────────────────────────────────────

    def fork(self, scope_kind: ScopeKind, scope_id: str) -> ScopedPluginHost:
        """Create a child scope.

        The child inherits visibility of all services in this scope
        (via parent delegation), but has its own service table for
        local overrides.
        """
        child = ScopedPluginHost(self, scope_kind, scope_id)
        self._children.append(child)
        return child

    # ── Async scope propagation ───────────────────────────

    async def run_in_scope(self, coro: Any) -> Any:
        """Run *coro* with this scope as the current scope.

        Inside *coro* (and any sub-tasks it creates), ``ScopedPluginHost.current()``
        returns this scope. This is the Python equivalent of DSH's fiber-scoped
        ``AsyncLocalStorage``.

        Implementation: ``contextvars.ContextVar`` is automatically copied by
        ``asyncio.create_task()``, so child tasks inherit the scope.
        """
        token = _current_scope.set(self)
        try:
            return await coro
        finally:
            _current_scope.reset(token)

    def run_in_scope_sync(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Synchronous variant for non-async callables."""
        token = _current_scope.set(self)
        try:
            return fn(*args, **kwargs)
        finally:
            _current_scope.reset(token)

    @staticmethod
    def current() -> ScopedPluginHost:
        """Get the current scope from the async context.

        Raises ``RuntimeError`` if called outside ``run_in_scope()``.
        """
        scope = _current_scope.get()
        if scope is None:
            raise RuntimeError(
                "No active plugin scope. Use scope.run_in_scope(coro) to enter a scope context."
            )
        return scope

    # ── Drain / cleanup ───────────────────────────────────

    async def drain(self) -> None:
        """Drain all children (LIFO), then clean up own resources.

        Parent cannot unload until all children have drained.
        """
        for child in reversed(self._children):
            await child.drain()
        self._children.clear()
        # Dispose all handles in this scope's host
        from lca.layer0_infra.plugin.kernel._lifecycle import shutdown

        await shutdown(self._host)

    def remove_child(self, child: ScopedPluginHost) -> None:
        """Remove a child scope (called after drain)."""
        with contextlib.suppress(ValueError):
            self._children.remove(child)


def current_scope() -> ScopedPluginHost:
    """Module-level convenience: get the current scope."""
    return ScopedPluginHost.current()
