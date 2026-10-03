"""Typed domain exceptions for connector execution (INV-CONN-02)."""

from __future__ import annotations


class ConnectionNotActiveError(RuntimeError):
    """Raised when an action is attempted on an external connector that is not in ACTIVE state.

    This exception is raised at the execution boundary without coupling to
    UI widgets or presentation format.
    """

    def __init__(self, service: str, user_id: str, state: str = "NOT_CONNECTED") -> None:
        super().__init__(f"Connector service {service!r} is not active for user {user_id!r} (current state: {state})")
        self.service = service
        self.user_id = user_id
        self.state = state
