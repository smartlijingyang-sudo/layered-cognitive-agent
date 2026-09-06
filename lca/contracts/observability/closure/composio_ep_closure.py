"""Composio domain EP closure — observability SSOT for connection + tool debug.

Follows ADR-0187 assistant pattern: frozen EP tuple + EventDescriptor metadata +
cordis_event_table entries. No skill/connection secrets in payload — ids and status only.
"""

from __future__ import annotations

from typing import Final

from lca.contracts.models.observability.event.event import (
    EventAudience,
    EventDescriptor,
    EventDurability,
    EventPlane,
    EventSensitivity,
)

COMPOSIO_OAUTH_CALLBACK_RECEIVED: Final[str] = "composio.oauth.callback.received"
COMPOSIO_OAUTH_CALLBACK_FAILED: Final[str] = "composio.oauth.callback.failed"
COMPOSIO_OAUTH_CALLBACK_PROCESSED: Final[str] = "composio.oauth.callback.processed"
COMPOSIO_CONNECTION_CREATED: Final[str] = "composio.connection.created"
COMPOSIO_CONNECTION_PENDING: Final[str] = "composio.connection.pending"
COMPOSIO_CONNECTION_REFRESHED: Final[str] = "composio.connection.refreshed"
COMPOSIO_CONNECTION_ACTIVATED: Final[str] = "composio.connection.activated"
COMPOSIO_CONNECTION_DELETED: Final[str] = "composio.connection.deleted"
COMPOSIO_TOOL_EXECUTION_STARTED: Final[str] = "composio.tool.execution.started"
COMPOSIO_TOOL_EXECUTED: Final[str] = "composio.tool.executed"
COMPOSIO_TOOL_EXECUTION_FAILED: Final[str] = "composio.tool.execution.failed"

COMPOSIO_EVENT_POINTS: Final[tuple[str, ...]] = (
    COMPOSIO_OAUTH_CALLBACK_RECEIVED,
    COMPOSIO_OAUTH_CALLBACK_FAILED,
    COMPOSIO_OAUTH_CALLBACK_PROCESSED,
    COMPOSIO_CONNECTION_CREATED,
    COMPOSIO_CONNECTION_PENDING,
    COMPOSIO_CONNECTION_REFRESHED,
    COMPOSIO_CONNECTION_ACTIVATED,
    COMPOSIO_CONNECTION_DELETED,
    COMPOSIO_TOOL_EXECUTION_STARTED,
    COMPOSIO_TOOL_EXECUTED,
    COMPOSIO_TOOL_EXECUTION_FAILED,
)

_COMPOSIO_EMITTER = "lca.plugins.integrations.composio"


def _composio_descriptor(type_name: str) -> EventDescriptor:
    return EventDescriptor(
        type_name=type_name,
        emitter=_COMPOSIO_EMITTER,
        description=f"Composio integration: {type_name}",
        plane=EventPlane.STRUCTURAL,
        domain="event",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=("identifier",),
    )


def all_composio_event_descriptors() -> tuple[EventDescriptor, ...]:
    """Return EventDescriptor metadata for boot-time registry registration."""
    return tuple(_composio_descriptor(ep) for ep in COMPOSIO_EVENT_POINTS)


__all__ = [
    "COMPOSIO_CONNECTION_ACTIVATED",
    "COMPOSIO_CONNECTION_CREATED",
    "COMPOSIO_CONNECTION_DELETED",
    "COMPOSIO_CONNECTION_PENDING",
    "COMPOSIO_CONNECTION_REFRESHED",
    "COMPOSIO_EVENT_POINTS",
    "COMPOSIO_OAUTH_CALLBACK_FAILED",
    "COMPOSIO_OAUTH_CALLBACK_PROCESSED",
    "COMPOSIO_OAUTH_CALLBACK_RECEIVED",
    "COMPOSIO_TOOL_EXECUTED",
    "COMPOSIO_TOOL_EXECUTION_FAILED",
    "COMPOSIO_TOOL_EXECUTION_STARTED",
    "all_composio_event_descriptors",
]
