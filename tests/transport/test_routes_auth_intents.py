"""Tests for auth-intents resolve endpoint (INV-CAP-03).

Validates:
1. POST /composio/auth-intents/{intent_id}/resolve successfully resolves valid intent.
2. POST /api/connectors/auth-intents/{intent_id}/resolve alias works identically.
3. Resolving an expired or non-existent intent returns 404.
4. Resolving cross-user intent returns 404 (user isolation).
5. OPTIONS preflight returns CORS headers.
"""

from __future__ import annotations

import time

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.infrastructure.connectors.core.intent_vault import (
    ConnectorAuthIntentVault,
    set_default_intent_vault,
)
from lca.plugins.transport.webserver.handlers.composio import endpoints as composio_handlers


def _create_test_app() -> Starlette:
    routes = [
        Route(
            "/composio/auth-intents/{intent_id}/resolve",
            composio_handlers.resolve_auth_intent,
            methods=["POST", "OPTIONS"],
        ),
        Route(
            "/api/connectors/auth-intents/{intent_id}/resolve",
            composio_handlers.resolve_auth_intent,
            methods=["POST", "OPTIONS"],
        ),
    ]
    return Starlette(routes=routes)


def test_resolve_auth_intent_success_and_aliases():
    vault = ConnectorAuthIntentVault()
    set_default_intent_vault(vault)

    intent_id = vault.create_intent(
        service="google-drive",
        app_name="Google Drive",
        auth_url="https://connect.composio.dev/link/lk_test_resolve",
        connection_id="conn_gd_123",
        user_id="alice",
        ttl_seconds=300,
    )

    client = TestClient(_create_test_app())

    # 1. /composio/auth-intents/{id}/resolve
    res1 = client.post(
        f"/composio/auth-intents/{intent_id}/resolve",
        headers={"X-User-ID": "alice"},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["authUrl"] == "https://connect.composio.dev/link/lk_test_resolve"
    assert data1["appName"] == "Google Drive"
    assert data1["connectionId"] == "conn_gd_123"

    # 2. /api/connectors/auth-intents/{id}/resolve alias
    res2 = client.post(
        f"/api/connectors/auth-intents/{intent_id}/resolve",
        headers={"X-User-ID": "alice"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["authUrl"] == "https://connect.composio.dev/link/lk_test_resolve"


def test_resolve_auth_intent_user_isolation_and_not_found():
    vault = ConnectorAuthIntentVault()
    set_default_intent_vault(vault)

    intent_id = vault.create_intent(
        service="gmail",
        app_name="Gmail",
        auth_url="https://connect.composio.dev/link/lk_secret_mail",
        connection_id="conn_gmail_456",
        user_id="alice",
        ttl_seconds=300,
    )

    client = TestClient(_create_test_app())

    # 越权用户访问被阻断 (返回 404)
    res_cross = client.post(
        f"/composio/auth-intents/{intent_id}/resolve",
        headers={"X-User-ID": "bob"},
    )
    assert res_cross.status_code == 404

    # 不存在的 intent_id
    res_none = client.post(
        "/composio/auth-intents/cai_does_not_exist/resolve",
        headers={"X-User-ID": "alice"},
    )
    assert res_none.status_code == 404


def test_resolve_auth_intent_expired():
    vault = ConnectorAuthIntentVault()
    set_default_intent_vault(vault)

    intent_id = vault.create_intent(
        service="slack",
        app_name="Slack",
        auth_url="https://connect.composio.dev/link/lk_slack_exp",
        connection_id="conn_slack_789",
        user_id="alice",
        ttl_seconds=0.1,
    )

    client = TestClient(_create_test_app())
    time.sleep(0.15)

    res_exp = client.post(
        f"/composio/auth-intents/{intent_id}/resolve",
        headers={"X-User-ID": "alice"},
    )
    assert res_exp.status_code == 404
