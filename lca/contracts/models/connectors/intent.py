"""Connector capability intent model — Zero Model Exposure (ADR-0280 / INV-CAP-02).

Enforces that high-privilege authorization URLs are never exposed to LLMs,
and instead represented by a capability intent ticket.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ConnectorAuthIntent(BaseModel):
    """Immutable capability ticket representing a pending authorization flow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: str
    service: str
    app_name: str
    auth_url: str
    connection_id: str
    user_id: str
    created_at: float
    expires_at: float
    consumed: bool = False

    def is_expired(self, current_time: float) -> bool:
        """Returns True if the intent has exceeded its expiration timestamp."""
        return current_time > self.expires_at

    def mark_consumed(self) -> ConnectorAuthIntent:
        """Returns a new ConnectorAuthIntent instance marked as consumed."""
        return self.model_copy(update={"consumed": True})


__all__ = ["ConnectorAuthIntent"]
