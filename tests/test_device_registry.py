"""DeviceRegistry persist + live channel semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lca.plugins.transport.device_gateway.auth import AuthError, verify_token
from lca.plugins.transport.device_gateway.bind import DeviceMachineResolver
from lca.plugins.transport.device_gateway.hub import DeviceHub
from lca.plugins.transport.device_gateway.models import DeviceConnection
from lca.plugins.transport.device_gateway.registry import DeviceRegistry
from lca.plugins.transport.device_gateway.settings import DeviceGatewaySettings


def test_register_is_idempotent(tmp_path: Path) -> None:
    registry = DeviceRegistry(str(tmp_path / "devices.db"))
    first = registry.register_device(
        device_id="d1",
        hostname="box",
        platform="linux",
        home="/home/u",
        workspace="/home/sandbox-user",
        user_id="local-dev-user",
    )
    second = registry.register_device(
        device_id="d1",
        hostname="box-2",
        platform="linux",
        home="/home/u",
        workspace="/home/sandbox-user",
        user_id="local-dev-user",
    )
    assert first is second
    assert second.hostname == "box-2"


def test_channel_attach_detach(tmp_path: Path) -> None:
    registry = DeviceRegistry(str(tmp_path / "devices.db"))
    registry.register_device(
        device_id="d1",
        hostname="box",
        platform="linux",
        home="/home/u",
        workspace="/home/sandbox-user",
        user_id="u1",
    )
    conn = DeviceConnection(
        connection_id="c1",
        channel="cli",
        connected_at=datetime.now(UTC),
        websocket=object(),
    )
    registry.attach_channel("d1", conn)
    assert registry.select_online("d1") is not None
    assert registry.summary()["online"] == 1
    registry.detach_channel("d1", "c1")
    assert registry.select_online("d1") is None
    assert registry.get("d1") is not None


def test_device_machine_resolver_is_bound_to_explicit_registry_and_hub(tmp_path: Path) -> None:
    registry = DeviceRegistry(str(tmp_path / "devices.db"))
    registry.register_device(
        device_id="d1",
        hostname="box",
        platform="linux",
        home="/home/u",
        workspace="/workspace",
        user_id="u1",
    )
    registry.attach_channel(
        "d1",
        DeviceConnection(
            connection_id="c1",
            channel="cli",
            connected_at=datetime.now(UTC),
            websocket=object(),
        ),
    )
    resolver = DeviceMachineResolver(registry, DeviceHub(registry))

    machine = resolver.resolve_machine("d1")

    assert machine is not None
    assert machine.id == "d1"
    assert machine.root == "/workspace"
    assert resolver.resolve_transport("d1") is not None


def test_workspace_pool(tmp_path: Path) -> None:
    registry = DeviceRegistry(str(tmp_path / "devices.db"))
    for device_id, user, workspace in (
        ("a", "u1", "ws-1"),
        ("b", "u2", "ws-1"),
        ("c", "u1", None),
    ):
        registry.register_device(
            device_id=device_id,
            hostname=device_id,
            platform="linux",
            home="/",
            workspace="/",
            user_id=user,
            workspace_id=workspace,
        )
        registry.attach_channel(
            device_id,
            DeviceConnection(
                connection_id=device_id,
                channel="cli",
                connected_at=datetime.now(UTC),
                websocket=object(),
            ),
        )
    pool = registry.list_online("u1", "ws-1")
    ids = {d.device_id for d in pool}
    assert ids == {"a", "b", "c"}
    personal = registry.list_online("u1")
    assert {d.device_id for d in personal} == {"a", "c"}


def test_service_token_auth() -> None:
    settings = DeviceGatewaySettings(service_token="secret", subject="local-dev-user")  # noqa: S106
    user = verify_token("secret", "serviceToken", settings)
    assert user.user_id == "local-dev-user"
    try:
        verify_token("nope", "serviceToken", settings)
    except AuthError:
        return
    raise AssertionError("expected AuthError")
