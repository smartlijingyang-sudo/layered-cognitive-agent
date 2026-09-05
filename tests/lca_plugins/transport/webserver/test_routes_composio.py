"""Tests for Composio HTTP routes and OAuth callback."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.infrastructure.integrations.composio.models import ComposioConnection, ComposioToolDef
from lca.infrastructure.integrations.composio.service import ComposioIntegration
from lca.infrastructure.integrations.composio.settings import ComposioSettings
from lca.plugins.transport.webserver.handlers.composio import endpoints as composio_handlers
from lca.plugins.transport.webserver.route_register import _instrument_route_handler


def _settings(tmp: Path) -> ComposioSettings:
    return ComposioSettings.from_plugin_config(
        api_key="test-key",
        connections_path=str(tmp / "connections.json"),
    )


def _client(integration: ComposioIntegration) -> TestClient:
    composio_handlers.bind_composio(integration)
    routes = [
        Route("/composio/oauth/callback", _instrument_route_handler(composio_handlers.oauth_callback, path="/composio/oauth/callback"), methods=["GET"]),
        Route("/composio/connections", _instrument_route_handler(composio_handlers.connections, path="/composio/connections"), methods=["GET", "POST", "OPTIONS"]),
        Route(
            "/composio/connections/by-account/{connected_account_id}",
            _instrument_route_handler(composio_handlers.connection_by_account, path="/composio/connections/by-account/{connected_account_id}"),
            methods=["GET", "OPTIONS"],
        ),
        Route(
            "/composio/connections/{identifier}/refresh",
            _instrument_route_handler(composio_handlers.connection_refresh, path="/composio/connections/{identifier}/refresh"),
            methods=["POST", "OPTIONS"],
        ),
        Route(
            "/composio/connections/{identifier}",
            _instrument_route_handler(composio_handlers.connection_by_identifier, path="/composio/connections/{identifier}"),
            methods=["DELETE", "OPTIONS"],
        ),
    ]
    return TestClient(Starlette(routes=routes))


@pytest.mark.asyncio
async def test_oauth_callback_refreshes_pending_connection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        integration = ComposioIntegration(_settings(tmp_path))
        integration.import_connection(
            ComposioConnection(
                identifier="google-drive",
                app_slug="GOOGLEDRIVE",
                label="Google Drive",
                connected_account_id="ca_pending",
                auth_config_id="ac_1",
                user_id="user-1",
                status="PENDING",
            )
        )
        with patch.object(
            integration,
            "refresh_connection",
            new=AsyncMock(
                return_value=ComposioConnection(
                    identifier="google-drive",
                    app_slug="GOOGLEDRIVE",
                    label="Google Drive",
                    connected_account_id="ca_pending",
                    auth_config_id="ac_1",
                    user_id="user-1",
                    status="ACTIVE",
                    tools=[ComposioToolDef(name="GOOGLEDRIVE_LIST_FILES", description="list")],
                )
            ),
        ) as refresh:
            client = _client(integration)
            response = client.get("/composio/oauth/callback?status=success&connected_account_id=ca_pending")
            assert response.status_code == 200
            assert "Authorization complete" in response.text
            refresh.assert_awaited_once_with("google-drive")


def test_list_connections_returns_plugin_shape() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        integration = ComposioIntegration(_settings(tmp_path))
        integration.import_connection(
            ComposioConnection(
                identifier="slack",
                app_slug="SLACK",
                label="Slack",
                connected_account_id="ca_slack",
                auth_config_id="ac_slack",
                user_id="user-1",
                status="ACTIVE",
                tools=[ComposioToolDef(name="SLACK_SEND", description="send")],
            )
        )
        client = _client(integration)
        response = client.get("/composio/connections")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["plugins"]) == 1
        assert payload["plugins"][0]["identifier"] == "slack"
        assert payload["plugins"][0]["customParams"]["composio"]["connectedAccountId"] == "ca_slack"


@pytest.mark.asyncio
async def test_routes_composio_plugin_registers_when_capability_present() -> None:
    from lca.contracts.mechanisms.capability import MissingCapabilityError
    from lca.plugins.transport.webserver.router import RouteRegistry

    class _FakeRuntime:
        def __init__(self) -> None:
            self.effects: list[tuple[object, str]] = []

        def effect(self, dispose: object, *, label: str = "effect") -> None:
            self.effects.append((dispose, label))

    class _FakeCtx:
        def __init__(self, router: RouteRegistry, integration: ComposioIntegration) -> None:
            self._router = router
            self._integration = integration
            self._fake_runtime = _FakeRuntime()

        def require(self, key: str) -> object:
            if key == "route_registry":
                return self._router
            if key == "composio":
                return self._integration
            raise MissingCapabilityError(key)

        def _runtime(self) -> _FakeRuntime:
            return self._fake_runtime

    with tempfile.TemporaryDirectory() as tmp:
        integration = ComposioIntegration(_settings(Path(tmp)))
        router = RouteRegistry()
        ctx = _FakeCtx(router, integration)
        from lca.plugins.transport.webserver.routes_composio import setup as plugin

        await plugin.setup(ctx, None)
        assert "/composio/oauth/callback" in router._exact
        assert "/composio/connections" in router._exact
