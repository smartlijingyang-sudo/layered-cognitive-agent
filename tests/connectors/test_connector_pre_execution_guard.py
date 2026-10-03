"""Tests for ConnectorPreExecutionGuard and layered ConnectionNotActiveError (INV-CONN-02)."""

from __future__ import annotations

from pathlib import Path
import pytest

from lca.infrastructure.connectors.core.exceptions import ConnectionNotActiveError
from lca.infrastructure.connectors.core.guard import ConnectorPreExecutionGuard
from lca.infrastructure.connectors.core.state import ConnectionState
from lca.infrastructure.connectors.core.vault import ConnectorVault


def test_guard_raises_typed_error_when_service_not_active(tmp_path: Path) -> None:
    """Execution layer: Guard must raise ConnectionNotActiveError without UI card coupling."""
    lca_home = tmp_path / ".lca"
    vault = ConnectorVault(user_id="user_alice", lca_home=lca_home)
    guard = ConnectorPreExecutionGuard(vault=vault)

    # Calling an action on unauthenticated google-drive must fail-closed with typed error
    with pytest.raises(ConnectionNotActiveError) as exc_info:
        guard.ensure_active(service="google-drive")

    err = exc_info.value
    assert err.service == "google-drive"
    assert err.user_id == "user_alice"
    assert err.state == ConnectionState.NOT_CONNECTED.value


def test_guard_passes_when_service_is_active(tmp_path: Path) -> None:
    """Execution layer: Guard passes without error when service is ACTIVE."""
    lca_home = tmp_path / ".lca"
    vault = ConnectorVault(user_id="user_bob", lca_home=lca_home)
    vault.upsert_connection(
        service="github",
        state=ConnectionState.ACTIVE,
        account_identity="bob_gh",
    )

    guard = ConnectorPreExecutionGuard(vault=vault)
    # Must not raise
    guard.ensure_active(service="github")


def test_adapter_translates_error_into_widget_observation() -> None:
    """Adapter layer: Catching ConnectionNotActiveError formats structured widget observation."""
    from lca.infrastructure.connectors.core.adapter import format_connection_not_active_observation

    err = ConnectionNotActiveError(service="google-drive", user_id="user_alice")
    obs = format_connection_not_active_observation(
        err,
        auth_url="https://backend.composio.dev/api/v3/auth/redirect?token=dummy_123",
        connection_id="ca_dummy_123",
    )

    assert obs.success is False
    assert obs.error == "SERVICE_NOT_CONNECTED"
    assert "widget" in obs.payload
    assert obs.payload["widget"].startswith("[widget:connector_auth?appName=Google+Drive")
