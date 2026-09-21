"""Ports for execution-environment discovery (hexagonal adapters).

``EnvironmentCatalog`` is the seam the prompt assembler and the
``listEnvironments`` tool depend on. ``EnvironmentProvider`` is the port each
environment source (cloud sandbox, companion devices, future SSH hosts)
implements. ``DeviceProvider`` is the minimal face the device adapter needs
from the device registry.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.models.core.environment.model import ExecutionEnvironment


@runtime_checkable
class EnvironmentProvider(Protocol):
    """One source of known execution environments."""

    def list_environments(self) -> list[ExecutionEnvironment]: ...


@runtime_checkable
class EnvironmentCatalog(Protocol):
    """Read-side directory over all known execution environments."""

    def list_all(self) -> list[ExecutionEnvironment]: ...

    def current(self) -> ExecutionEnvironment | None: ...


@runtime_checkable
class DeviceProvider(Protocol):
    """Minimal device-registry face for building machine environments."""

    def list_devices(self) -> list[dict[str, Any]]: ...


__all__ = ["DeviceProvider", "EnvironmentCatalog", "EnvironmentProvider"]
