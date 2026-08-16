"""PluginHost — pure data container for the plugin runtime.

Responsibilities (ONLY these, nothing more):
- Own the service table (``_services: dict[str, ServiceRecord]``)
- Own the event bus (``events: EventBus``)
- Own the handle registry (``_handles: dict[str, PluginHandle]``)
- Provide CRUD: mount/get/remove services, register/unregister handles

NO lifecycle logic. No reconcile. No activate. No deactivate.
Those belong to ``_lifecycle.py`` — the state machine driver.

This separation ensures host stays a simple container that can be
tested, replaced, or extended without touching lifecycle code.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from lca.layer0_infra.plugin.kernel._events import EventBus
from lca.layer0_infra.plugin.kernel._handle import PluginHandle
from lca.layer0_infra.plugin.kernel._service_record import ServiceRecord
from lca.layer0_infra.plugin.kernel._types import PluginError


class PluginHost:
    """Plugin container: service table + event bus + handle registry."""

    def __init__(self) -> None:
        self._services: dict[str, ServiceRecord] = {}
        self._handles: dict[str, PluginHandle] = {}
        self.events: EventBus = EventBus()
        self.builtins: dict[str, Any] = {}

    # ── Handle registry ───────────────────────────────────

    @property
    def handles(self) -> Mapping[str, PluginHandle]:
        """Read-only view of all registered handles."""
        return self._handles

    def register_handle(self, handle: PluginHandle) -> None:
        """Register a handle. Duplicate entry_id → PluginError."""
        if handle.entry_id in self._handles:
            raise PluginError(f"Duplicate entry id: {handle.entry_id!r}")
        self._handles[handle.entry_id] = handle

    def unregister_handle(self, entry_id: str) -> PluginHandle | None:
        """Remove and return a handle by entry_id."""
        return self._handles.pop(entry_id, None)

    # ── Service table ─────────────────────────────────────

    def provide(
        self,
        handle: PluginHandle,
        name: str,
        value: Any,
        check: Callable[[], bool] | None = None,
    ) -> None:
        """Mount a service owned by *handle*. Duplicate key → PluginError."""
        if not name:
            raise ValueError("capability key is empty")
        if name in self._services:
            existing = self._services[name]
            if existing.owner_id != handle.entry_id:
                raise PluginError(f"Service {name!r} already provided by {existing.owner_id!r}")
            # Same owner re-providing: update value
            existing.value = value
            return
        record = ServiceRecord(name=name, value=value, owner_id=handle.entry_id, check=check)
        self._services[name] = record
        handle.provided_services.add(name)

    def get_service(self, name: str, default: Any = None) -> Any:
        """Look up a service by name. Returns default if missing/unavailable.

        Does NOT check owner handle state — that is the lifecycle layer's
        responsibility (cascade deactivation handles it).
        """
        record = self._services.get(name)
        if record is None or not record.available:
            return default
        return record.value

    def get_service_record(self, name: str) -> ServiceRecord | None:
        """Raw service record lookup (includes unavailable)."""
        return self._services.get(name)

    def remove_service(self, name: str) -> None:
        """Remove a service from the table."""
        self._services.pop(name, None)

    def remove_owned_services(self, handle: PluginHandle) -> list[str]:
        """Remove all services owned by *handle*. Return removed names."""
        removed: list[str] = []
        for name in list(handle.provided_services):
            record = self._services.get(name)
            if record is not None and record.owner_id == handle.entry_id:
                self._services.pop(name, None)
                removed.append(name)
            handle.provided_services.discard(name)
        return removed
