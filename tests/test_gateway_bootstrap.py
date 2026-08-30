"""Gateway startup infrastructure must be explicit and app-scoped."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import cast

import pytest

from gateway.app import create_app
from gateway.bootstrap import (
    DefaultGatewayBootstrapFactory,
    GatewayBootstrap,
    GatewayBootstrapConfig,
    GatewayBootstrapFactory,
)
from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.registry import DeviceRegistry
from gateway.device_gateway.settings import DeviceGatewaySettings
from lca.contracts.models.core.plane import PlaneRef
from lca.contracts.protocols.infra import MachineResolver, MachineTransport
from lca.infrastructure.file_store import LocalFileStore


class _EmptyMachineResolver(MachineResolver):
    def resolve_machine(self, device_id: str | None = None) -> PlaneRef | None:
        del device_id
        return None

    def resolve_transport(self, device_id: str) -> MachineTransport | None:
        del device_id
        return None


class _FixedBootstrapFactory(GatewayBootstrapFactory):
    def __init__(self, product: GatewayBootstrap) -> None:
        self.product = product
        self.received: GatewayBootstrapConfig | None = None

    def create(self, config: GatewayBootstrapConfig) -> GatewayBootstrap:
        self.received = config
        return self.product


def test_create_app_installs_exact_bootstrap_product_instances() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalFileStore(Path(tmpdir) / "files")
        resolver = _EmptyMachineResolver()
        product = GatewayBootstrap(
            file_store=store,
            devices=cast("DeviceRegistry", object()),
            device_hub=cast("DeviceHub", object()),
            machine_resolver=resolver,
            device_settings=DeviceGatewaySettings(db_path=str(Path(tmpdir) / "devices.db")),
        )
        factory = _FixedBootstrapFactory(product)
        config = GatewayBootstrapConfig(file_store_root=Path(tmpdir) / "configured-files")

        app = create_app(profile_path=None, bootstrap_factory=factory, bootstrap_config=config)

    assert factory.received is config
    assert app.state.bootstrap is product
    assert app.state.file_store is store
    assert app.state.devices is product.devices
    assert app.state.device_hub is product.device_hub
    assert app.state.machine_resolver is resolver


@pytest.mark.asyncio
async def test_gateway_lifespan_reuses_bootstrap_file_store() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalFileStore(Path(tmpdir) / "files")
        product = GatewayBootstrap(
            file_store=store,
            devices=cast("DeviceRegistry", object()),
            device_hub=cast("DeviceHub", object()),
            machine_resolver=_EmptyMachineResolver(),
            device_settings=DeviceGatewaySettings(db_path=str(Path(tmpdir) / "devices.db")),
        )
        app = create_app(
            profile_path="profiles/web-standard.yaml",
            bootstrap_factory=_FixedBootstrapFactory(product),
        )
        async with app.router.lifespan_context(app):
            assert app.state.ctx.inject("file_store").current() is store


def test_default_bootstrap_factory_creates_isolated_app_resources() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        factory = DefaultGatewayBootstrapFactory()
        first = factory.create(
            GatewayBootstrapConfig(
                file_store_root=root / "one-files",
                device_settings=DeviceGatewaySettings(db_path=str(root / "one-devices.db")),
            )
        )
        second = factory.create(
            GatewayBootstrapConfig(
                file_store_root=root / "two-files",
                device_settings=DeviceGatewaySettings(db_path=str(root / "two-devices.db")),
            )
        )

    assert first.file_store is not second.file_store
    assert first.devices is not second.devices
    assert first.device_hub is not second.device_hub
    assert first.machine_resolver is not second.machine_resolver


