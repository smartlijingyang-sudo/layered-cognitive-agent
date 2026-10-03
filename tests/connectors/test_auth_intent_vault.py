"""Tests for ConnectorAuthIntent and ConnectorAuthIntentVault (INV-CAP-02).

Validates:
1. ConnectorAuthIntent model contracts (frozen, extra=forbid).
2. Intent creation and resolution within TTL.
3. Multi-tenant isolation (cross-user resolution rejected).
4. Expiration after TTL (auto-expiry).
5. Single-consume / idempotent audit tracking.
6. Singleton registry access.
"""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from lca.contracts.models.connectors.intent import ConnectorAuthIntent
from lca.infrastructure.connectors.core.intent_vault import (
    ConnectorAuthIntentVault,
    get_default_intent_vault,
    set_default_intent_vault,
)


def test_connector_auth_intent_model_immutability():
    intent = ConnectorAuthIntent(
        intent_id="cai_test123456",
        service="google-drive",
        app_name="Google Drive",
        auth_url="https://connect.composio.dev/link/lk_test",
        connection_id="conn_1",
        user_id="user_alice",
        created_at=time.time(),
        expires_at=time.time() + 300,
        consumed=False,
    )
    assert intent.intent_id == "cai_test123456"
    assert intent.app_name == "Google Drive"

    # 必须不可变
    with pytest.raises(ValidationError):
        intent.consumed = True  # type: ignore[misc]

    # 禁止额外字段
    with pytest.raises(ValidationError):
        ConnectorAuthIntent(
            intent_id="cai_test",
            service="google-drive",
            app_name="Google Drive",
            auth_url="https://connect.composio.dev/link/lk_test",
            connection_id="conn_1",
            user_id="user_alice",
            created_at=time.time(),
            expires_at=time.time() + 300,
            consumed=False,
            unexpected_field="hack",  # type: ignore[call-arg]
        )


def test_intent_vault_create_and_resolve_lifecycle():
    vault = ConnectorAuthIntentVault()
    intent_id = vault.create_intent(
        service="google-drive",
        app_name="Google Drive",
        auth_url="https://connect.composio.dev/link/lk_alpha",
        connection_id="conn_alpha",
        user_id="user_alice",
        ttl_seconds=1,
    )
    assert intent_id.startswith("cai_")

    # 正常用户在有效期内获取
    resolved = vault.resolve_intent(intent_id, user_id="user_alice")
    assert resolved is not None
    assert resolved.auth_url == "https://connect.composio.dev/link/lk_alpha"
    assert resolved.app_name == "Google Drive"
    assert resolved.service == "google-drive"
    assert resolved.consumed is True

    # 相同用户二次获取仍返回记录（标记已消费），由上层决定是否放行或仅审计
    second_fetch = vault.resolve_intent(intent_id, user_id="user_alice")
    assert second_fetch is not None
    assert second_fetch.consumed is True


def test_intent_vault_multi_tenant_isolation():
    vault = ConnectorAuthIntentVault()
    intent_id = vault.create_intent(
        service="gmail",
        app_name="Gmail",
        auth_url="https://connect.composio.dev/link/lk_secret",
        connection_id="conn_secret",
        user_id="user_alice",
        ttl_seconds=60,
    )

    # 跨用户窃取被拒绝
    assert vault.resolve_intent(intent_id, user_id="user_bob") is None
    assert vault.resolve_intent(intent_id, user_id="anonymous") is None
    assert vault.resolve_intent(intent_id, user_id="") is None


def test_intent_vault_expiration():
    vault = ConnectorAuthIntentVault()
    intent_id = vault.create_intent(
        service="slack",
        app_name="Slack",
        auth_url="https://connect.composio.dev/link/lk_slack",
        connection_id="conn_slack",
        user_id="user_alice",
        ttl_seconds=0.1,  # 100ms
    )

    time.sleep(0.15)
    assert vault.resolve_intent(intent_id, user_id="user_alice") is None


def test_default_intent_vault_singleton():
    v1 = get_default_intent_vault()
    v2 = get_default_intent_vault()
    assert v1 is v2

    custom = ConnectorAuthIntentVault()
    set_default_intent_vault(custom)
    assert get_default_intent_vault() is custom
    # 恢复
    set_default_intent_vault(v1)
