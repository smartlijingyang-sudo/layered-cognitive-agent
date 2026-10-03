"""Tests for Zero Model URL Exposure in tools and adapters (INV-CAP-01).

Validates:
1. composioConnect tool execution yields Observation with intent_id and NO http/https auth links.
2. format_connection_not_active_observation yields Observation with intent_id and NO http/https links.
3. widget_tag in payload strictly uses intentId instead of authUrl.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.infrastructure.connectors.core.adapter import format_connection_not_active_observation
from lca.infrastructure.connectors.core.exceptions import ConnectionNotActiveError
from lca.infrastructure.connectors.core.intent_vault import (
    ConnectorAuthIntentVault,
    set_default_intent_vault,
)
from lca.infrastructure.connectors.core.state import format_connector_auth_widget
from lca.infrastructure.integrations.composio.service.service import ComposioConnection
from lca.infrastructure.tools.composio import ComposioManagementExecutor


def test_format_connector_auth_widget_with_intent_id():
    widget = format_connector_auth_widget(
        app_name="Google Drive",
        connection_id="conn_123",
        intent_id="cai_test987",
    )
    assert "[widget:connector_auth?" in widget
    assert "intentId=cai_test987" in widget
    assert "appName=Google+Drive" in widget
    # 绝对不含 authUrl
    assert "authUrl" not in widget


@pytest.mark.asyncio
async def test_composio_connect_zero_url_leakage():
    vault = ConnectorAuthIntentVault()
    set_default_intent_vault(vault)

    # 模拟未连接的 Composio 返回
    mock_integration = MagicMock()
    mock_integration.get_connection.return_value = None

    fake_conn = ComposioConnection(
        identifier="google-drive",
        app_slug="google-drive",
        label="Google Drive",
        connected_account_id="conn_account_xyz",
        auth_config_id="auth_cfg_123",
        user_id="test_user_01",
        status="PENDING",
        redirect_url="https://connect.composio.dev/link/lk_topsecret_oauth_link",
    )
    mock_integration.create_connection = AsyncMock(return_value=fake_conn)
    mock_integration.user_id = "test_user_01"

    executor = ComposioManagementExecutor(mock_integration)
    obs = await executor.composioConnect({"service": "google-drive"})

    assert obs.success is True
    payload = obs.payload

    # 核心不变量：LLM 看到的 text 与 payload 绝无 http/https 敏感短链
    assert "https://connect.composio.dev" not in payload["text"]
    assert "http://" not in payload["text"]
    assert "https://" not in payload["text"]
    assert "redirect_url" not in payload or not payload["redirect_url"]

    # 包含 intent 凭证与卡片挂载引导
    assert "intent_id" in payload
    assert payload["intent_id"].startswith("cai_")
    assert "widget_tag" in payload
    assert "intentId=" in payload["widget_tag"]
    assert "authUrl" not in payload["widget_tag"]

    # 校验该 intent_id 确已入库并能在 Vault 中兑换
    resolved = vault.resolve_intent(payload["intent_id"], user_id="test_user_01")
    assert resolved is not None
    assert resolved.auth_url == "https://connect.composio.dev/link/lk_topsecret_oauth_link"


def test_format_connection_not_active_observation_zero_url_leakage():
    vault = ConnectorAuthIntentVault()
    set_default_intent_vault(vault)

    err = ConnectionNotActiveError(service="gmail", user_id="alice")
    obs = format_connection_not_active_observation(
        err,
        auth_url="https://connect.composio.dev/link/lk_gmail_secret",
        connection_id="conn_gm_99",
    )

    assert obs.success is False
    payload = obs.payload

    # 核心不变量：绝无 http/https 敏感短链泄露在 text
    assert "http://" not in payload["text"]
    assert "https://" not in payload["text"]
    assert "intent_id" in payload
    assert payload["intent_id"].startswith("cai_")
    assert "widget" in payload
    assert "intentId=" in payload["widget"]
    assert "authUrl" not in payload["widget"]

    # 可以在 Vault 中兑换
    resolved = vault.resolve_intent(payload["intent_id"], user_id="alice")
    assert resolved is not None
    assert resolved.auth_url == "https://connect.composio.dev/link/lk_gmail_secret"
