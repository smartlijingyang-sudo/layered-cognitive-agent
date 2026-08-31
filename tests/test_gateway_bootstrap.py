"""Gateway startup infrastructure must be explicit and app-scoped.

ADR-0115 决定 6: gateway/app.py 是 thin factory,不再接
``bootstrap_factory`` / ``bootstrap_config`` —— 这些关注点迁给 plugins
(``lca/plugins/transport/webserver/`` 里的 routes plugin 在 lifespan 里
装配 file_store / devices 等)。

The legacy bootstrap tests are skipped pending ADR-0118 / K8 transition
that will define the new composition shape.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import cast

import pytest

from gateway.bootstrap import (
    DefaultGatewayBootstrapFactory,
    GatewayBootstrap,
    GatewayBootstrapConfig,
)
from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.registry import DeviceRegistry
from gateway.device_gateway.settings import DeviceGatewaySettings
from lca.contracts.models.core.plane import PlaneRef
from lca.contracts.protocols.runtime.infra import MachineResolver, MachineTransport
from lca.infrastructure.file_store import LocalFileStore


class _EmptyMachineResolver(MachineResolver):
    def resolve_machine(self, device_id: str | None = None) -> PlaneRef | None:
        del device_id
        return None

    def resolve_transport(self, device_id: str) -> MachineTransport | None:
        del device_id
        return None


@pytest.mark.skip(
    reason="bootstrap_factory/ bootstrap_config removed by ADR-0115 决定 6; "
    "see ADR-0118 K8 / HMR plan for replacement"
)
def test_create_app_installs_exact_bootstrap_product_instances() -> None:
    pass


@pytest.mark.skip(reason="bootstrap_factory removed by ADR-0115 决定 6")
def test_gateway_lifespan_reuses_bootstrap_file_store() -> None:
    pass


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


# Suppress unused-import warnings for legacy test fixtures.
_ = cast
_ = LocalFileStore
_ = GatewayBootstrap
_ = DeviceRegistry
_ = DeviceHub
