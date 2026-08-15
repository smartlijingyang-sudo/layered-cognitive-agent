"""Pydantic models for DSH JSON-RPC notifications and turn results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DshNotification(BaseModel):
    """One JSON-RPC notification from the DSH runtime."""

    model_config = ConfigDict(extra="ignore")

    method: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def session_event(self) -> dict[str, Any] | None:
        if self.method != "session.event":
            return None
        event = self.payload.get("event")
        return event if isinstance(event, dict) else None


class DshTurnResult(BaseModel):
    """Terminal facts of one DSH session.run interval."""

    model_config = ConfigDict(extra="ignore")

    session_id: str
    final_response: str = ""
    finish_reason: str | None = None
