"""Tests for LCA-native Composio integration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from lca.infrastructure.integrations.composio.catalog import (
    get_app_by_identifier,
    resolve_identifier_for_tool_slug,
)
from lca.infrastructure.integrations.composio.connection_store import ComposioConnectionStore
from lca.infrastructure.integrations.composio.models import ComposioConnection, ComposioToolDef
from lca.infrastructure.integrations.composio.settings import ComposioSettings
from lca.infrastructure.tools.composio import build_tools
from lca.plugins.transport.webserver.handlers.runs.wire.wire import resolve


class TestComposioCatalog(unittest.TestCase):
    def test_google_drive_identifier(self) -> None:
        app = get_app_by_identifier("google-drive")
        self.assertIsNotNone(app)
        assert app is not None
        self.assertEqual(app.app_slug, "GOOGLEDRIVE")

    def test_resolve_slug_to_identifier(self) -> None:
        self.assertEqual(resolve_identifier_for_tool_slug("GOOGLEDRIVE_LIST_FILES"), "google-drive")


class TestComposioConnectionStore(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "connections.json"
            store = ComposioConnectionStore(path)
            conn = ComposioConnection(
                identifier="google-drive",
                app_slug="GOOGLEDRIVE",
                label="Google Drive",
                connected_account_id="ca_test",
                auth_config_id="ac_test",
                user_id="user-1",
                status="ACTIVE",
                tools=[ComposioToolDef(name="GOOGLEDRIVE_LIST_FILES", description="list")],
            )
            store.upsert(conn)
            loaded = store.get("google-drive")
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.connected_account_id, "ca_test")
            self.assertEqual(loaded.tools[0].name, "GOOGLEDRIVE_LIST_FILES")


class TestComposioTools(unittest.IsolatedAsyncioTestCase):
    async def test_connect_unknown_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = ComposioSettings.from_plugin_config(
                api_key="test-key",
                connections_path=str(Path(tmp) / "connections.json"),
            )
            from lca.infrastructure.integrations.composio.service import ComposioIntegration

            integration = ComposioIntegration(settings)
            tool = next(t for t in build_tools(integration) if t.name == "composioConnect")
            obs = await tool.execute({"service": "not-a-real-service"})
            self.assertFalse(obs.success)

    async def test_dynamic_action_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "connections.json"
            store = ComposioConnectionStore(path)
            store.upsert(
                ComposioConnection(
                    identifier="google-drive",
                    app_slug="GOOGLEDRIVE",
                    label="Google Drive",
                    connected_account_id="ca_1",
                    auth_config_id="ac_1",
                    user_id="user-1",
                    status="ACTIVE",
                    tools=[ComposioToolDef(name="GOOGLEDRIVE_LIST_FILES", description="list files")],
                )
            )
            settings = ComposioSettings.from_plugin_config(
                api_key="test-key",
                connections_path=str(path),
            )
            from lca.infrastructure.integrations.composio.service import ComposioIntegration

            integration = ComposioIntegration(settings)
            tools = build_tools(integration)
            action = next(t for t in tools if t.name == "GOOGLEDRIVE_LIST_FILES")
            with patch.object(
                integration,
                "execute_action",
                new=AsyncMock(return_value=json.dumps({"files": []})),
            ):
                obs = await action.execute({})
            self.assertTrue(obs.success)
            self.assertIn("files", str(obs.payload))


class TestComposioWire(unittest.TestCase):
    def test_management_tools(self) -> None:
        self.assertEqual(resolve("composioConnect"), ("composio", "composioConnect"))
        self.assertEqual(resolve("composioRefresh"), ("composio", "composioRefresh"))

    def test_dynamic_action(self) -> None:
        self.assertEqual(resolve("GOOGLEDRIVE_LIST_FILES"), ("google-drive", "GOOGLEDRIVE_LIST_FILES"))


class TestComposioOAuthCallback(unittest.IsolatedAsyncioTestCase):
    async def test_handle_oauth_callback_by_account_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = ComposioSettings.from_plugin_config(
                api_key="test-key",
                connections_path=str(Path(tmp) / "connections.json"),
            )
            from lca.infrastructure.integrations.composio.service import ComposioIntegration

            integration = ComposioIntegration(settings)
            integration.import_connection(
                ComposioConnection(
                    identifier="gmail",
                    app_slug="GMAIL",
                    label="Gmail",
                    connected_account_id="ca_gmail",
                    auth_config_id="ac_gmail",
                    user_id="user-1",
                    status="PENDING",
                )
            )
            with patch.object(
                integration,
                "refresh_connection",
                new=AsyncMock(
                    return_value=ComposioConnection(
                        identifier="gmail",
                        app_slug="GMAIL",
                        label="Gmail",
                        connected_account_id="ca_gmail",
                        auth_config_id="ac_gmail",
                        user_id="user-1",
                        status="ACTIVE",
                    )
                ),
            ) as refresh:
                refreshed = await integration.handle_oauth_callback(
                    connected_account_id="ca_gmail",
                    status="success",
                )
                self.assertEqual(len(refreshed), 1)
                refresh.assert_awaited_once_with("gmail")


class TestComposioMigration(unittest.TestCase):
    def test_row_to_connection_from_plugin_row(self) -> None:
        from lca.infrastructure.integrations.composio.migrate_lobehub import row_to_connection

        conn = row_to_connection(
            {
                "identifier": "google-drive",
                "custom_params": {
                    "composio": {
                        "appSlug": "GOOGLEDRIVE",
                        "authConfigId": "ac_1",
                        "connectedAccountId": "ca_1",
                        "status": "ACTIVE",
                    }
                },
                "manifest": {
                    "api": [{"name": "GOOGLEDRIVE_LIST_FILES", "description": "list"}],
                },
            }
        )
        self.assertIsNotNone(conn)
        assert conn is not None
        self.assertEqual(conn.identifier, "google-drive")
        self.assertEqual(conn.tools[0].name, "GOOGLEDRIVE_LIST_FILES")
