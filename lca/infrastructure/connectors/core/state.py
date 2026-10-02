"""Connector State Machine and Metadata Contracts (INV-01, INV-02, INV-03)."""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field


class ConnectionState(StrEnum):
    """Lifecycle state of a connector integration."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_CONNECTED = "NOT_CONNECTED"
    AWAITING_AUTH = "AWAITING_AUTH"
    ACTIVE = "ACTIVE"
    ADDITIONAL_ACCESS = "ADDITIONAL_ACCESS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"  # noqa: S105
    RATE_LIMITED = "RATE_LIMITED"


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal connector state transition is attempted."""


class ConnectionMetadata(BaseModel):
    """Metadata representing an active or pending connector instance.

    Guarantees INV-01: Extra fields are strictly forbidden to prevent
    sensitive OAuth tokens from ever leaking into memory or serialization.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    account_id: str = "default"
    state: ConnectionState
    connection_id: str | None = None
    auth_url: str | None = None
    scopes: list[str] = Field(default_factory=list)
    created_at: float | None = None


# Legal state transition directed graph
_VALID_TRANSITIONS: dict[ConnectionState, set[ConnectionState]] = {
    ConnectionState.NOT_CONFIGURED: {ConnectionState.NOT_CONNECTED},
    ConnectionState.NOT_CONNECTED: {ConnectionState.AWAITING_AUTH, ConnectionState.ACTIVE},
    ConnectionState.AWAITING_AUTH: {ConnectionState.ACTIVE, ConnectionState.NOT_CONNECTED},
    ConnectionState.ACTIVE: {
        ConnectionState.ADDITIONAL_ACCESS,
        ConnectionState.TOKEN_EXPIRED,
        ConnectionState.RATE_LIMITED,
        ConnectionState.NOT_CONNECTED,
    },
    ConnectionState.ADDITIONAL_ACCESS: {ConnectionState.ACTIVE, ConnectionState.NOT_CONNECTED},
    ConnectionState.TOKEN_EXPIRED: {ConnectionState.AWAITING_AUTH, ConnectionState.NOT_CONNECTED},
    ConnectionState.RATE_LIMITED: {ConnectionState.ACTIVE, ConnectionState.NOT_CONNECTED},
}


class ConnectorStateMachine:
    """Manages connector connection lifecycle and verifies legal state transitions."""

    def __init__(self, initial_state: ConnectionState = ConnectionState.NOT_CONNECTED) -> None:
        self._state = initial_state

    @property
    def state(self) -> ConnectionState:
        return self._state

    def can_transition_to(self, new_state: ConnectionState) -> bool:
        allowed = _VALID_TRANSITIONS.get(self._state, set())
        return new_state in allowed

    def transition_to(self, new_state: ConnectionState) -> None:
        if not self.can_transition_to(new_state):
            raise InvalidStateTransitionError(
                f"Invalid transition from {self._state.value} to {new_state.value}"
            )
        self._state = new_state


def format_connector_auth_widget(
    app_name: str,
    auth_url: str,
    connection_id: str,
) -> str:
    """Formats standard LobeHub ConnectorAuthCard widget markup (INV-03).

    Strictly produces widget syntax to trigger LobeHub's interactive card,
    preventing fallback to raw Markdown links.
    """
    params = urlencode(
        {
            "appName": app_name,
            "authUrl": auth_url,
            "connectionId": connection_id,
        }
    )
    return f"[widget:connector_auth?{params}]"
