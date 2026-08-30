"""Gateway startup infrastructure composition.

This module owns application-process infrastructure that must exist before the
Profile lifespan starts.  It deliberately has no module-level resource
singletons: every ``create_app`` call receives one explicit bootstrap product.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from gateway.device_gateway.bind import DeviceMachineResolver
from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.registry import DeviceRegistry
from gateway.device_gateway.settings import DeviceGatewaySettings
from lca.contracts.protocols.runtime.infra import MachineResolver
from lca.infrastructure.file_store import FileStore, LocalFileStore


@dataclass(frozen=True, slots=True)
class GatewayBootstrapConfig:
    """Concrete locations and URL policy for Gateway-owned infrastructure."""

    file_store_root: Path = Path("traces/files")
    file_store_url_prefix: str = "/files"
    device_settings: DeviceGatewaySettings | None = None


@dataclass(frozen=True, slots=True)
class GatewayBootstrap:
    """Explicit ownership bundle installed on one Starlette application."""

    file_store: FileStore
    devices: DeviceRegistry
    device_hub: DeviceHub
    machine_resolver: MachineResolver
    device_settings: DeviceGatewaySettings


@runtime_checkable
class GatewayBootstrapFactory(Protocol):
    """Create the application-scoped infrastructure used by Gateway routes."""

    def create(self, config: GatewayBootstrapConfig) -> GatewayBootstrap: ...


class DefaultGatewayBootstrapFactory(GatewayBootstrapFactory):
    """Filesystem and SQLite default for local Gateway deployment."""

    def create(self, config: GatewayBootstrapConfig) -> GatewayBootstrap:
        settings = config.device_settings or DeviceGatewaySettings()
        file_store = LocalFileStore(
            config.file_store_root,
            public_url_prefix=config.file_store_url_prefix,
        )
        devices = DeviceRegistry(settings.db_path)
        device_hub = DeviceHub(devices)
        machine_resolver = DeviceMachineResolver(devices, device_hub)
        return GatewayBootstrap(
            file_store=file_store,
            devices=devices,
            device_hub=device_hub,
            machine_resolver=machine_resolver,
            device_settings=settings,
        )


__all__ = [
    "DefaultGatewayBootstrapFactory",
    "GatewayBootstrap",
    "GatewayBootstrapConfig",
    "GatewayBootstrapFactory",
]
