"""Tests for Connector State Machine & Metadata Contracts (INV-01, INV-02, INV-03)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.infrastructure.connectors.core.state import (
    ConnectionMetadata,
    ConnectionState,
    ConnectorStateMachine,
    InvalidStateTransitionError,
    format_connector_auth_widget,
)


def test_connection_state_enum_members() -> None:
    expected = {
        "NOT_CONFIGURED",
        "NOT_CONNECTED",
        "AWAITING_AUTH",
        "ACTIVE",
        "ADDITIONAL_ACCESS",
        "TOKEN_EXPIRED",
        "RATE_LIMITED",
    }
    actual = {s.value for s in ConnectionState}
    assert actual == expected


def test_connection_metadata_model_frozen_and_valid() -> None:
    meta = ConnectionMetadata(
        service="gmail",
        account_id="work",
        state=ConnectionState.ACTIVE,
        connection_id="ca_test123",
        auth_url=None,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    assert meta.service == "gmail"
    assert meta.account_id == "work"
    assert meta.state == ConnectionState.ACTIVE
    assert meta.connection_id == "ca_test123"

    # Frozen immutability check
    with pytest.raises(ValidationError):
        meta.state = ConnectionState.RATE_LIMITED  # type: ignore[misc]


def test_connection_metadata_inv01_zero_token_exposure() -> None:
    """INV-01: Metadata model must forbid extra secret fields (e.g. access_token)."""
    with pytest.raises(ValidationError):
        ConnectionMetadata(
            service="gmail",
            account_id="work",
            state=ConnectionState.ACTIVE,
            connection_id="ca_test123",
            access_token="secret_token_12345",  # type: ignore[call-arg]  # noqa: S106
        )


def test_state_machine_valid_transitions() -> None:
    sm = ConnectorStateMachine(initial_state=ConnectionState.NOT_CONNECTED)
    assert sm.state == ConnectionState.NOT_CONNECTED

    # NOT_CONNECTED -> AWAITING_AUTH
    sm.transition_to(ConnectionState.AWAITING_AUTH)
    assert sm.state == ConnectionState.AWAITING_AUTH

    # AWAITING_AUTH -> ACTIVE
    sm.transition_to(ConnectionState.ACTIVE)
    assert sm.state == ConnectionState.ACTIVE

    # ACTIVE -> ADDITIONAL_ACCESS
    sm.transition_to(ConnectionState.ADDITIONAL_ACCESS)
    assert sm.state == ConnectionState.ADDITIONAL_ACCESS

    # ADDITIONAL_ACCESS -> ACTIVE
    sm.transition_to(ConnectionState.ACTIVE)
    assert sm.state == ConnectionState.ACTIVE

    # ACTIVE -> RATE_LIMITED
    sm.transition_to(ConnectionState.RATE_LIMITED)
    assert sm.state == ConnectionState.RATE_LIMITED

    # RATE_LIMITED -> ACTIVE
    sm.transition_to(ConnectionState.ACTIVE)
    assert sm.state == ConnectionState.ACTIVE

    # ACTIVE -> TOKEN_EXPIRED
    sm.transition_to(ConnectionState.TOKEN_EXPIRED)
    assert sm.state == ConnectionState.TOKEN_EXPIRED

    # TOKEN_EXPIRED -> AWAITING_AUTH
    sm.transition_to(ConnectionState.AWAITING_AUTH)
    assert sm.state == ConnectionState.AWAITING_AUTH


def test_state_machine_invalid_transition_fails_loudly() -> None:
    sm = ConnectorStateMachine(initial_state=ConnectionState.NOT_CONNECTED)

    # NOT_CONNECTED cannot jump directly to RATE_LIMITED
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        sm.transition_to(ConnectionState.RATE_LIMITED)
    assert "Invalid transition from NOT_CONNECTED to RATE_LIMITED" in str(exc_info.value)


def test_format_connector_auth_widget_inv03() -> None:
    """INV-03: Must generate LobeHub [widget:connector_auth?...] syntax, not raw markdown."""
    widget = format_connector_auth_widget(
        app_name="Gmail",
        auth_url="https://backend.composio.dev/auth?token=ca_123",
        connection_id="ca_123",
    )
    assert widget.startswith("[widget:connector_auth?")
    assert "appName=Gmail" in widget
    assert "connectionId=ca_123" in widget
    assert "authUrl=" in widget
    assert not widget.startswith("[Connect Gmail]")  # Strict anti-regression
