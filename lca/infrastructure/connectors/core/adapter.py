"""Connector presentation adapter — translates execution errors to UI observations."""

from __future__ import annotations

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.infrastructure.connectors.core.exceptions import ConnectionNotActiveError
from lca.infrastructure.connectors.core.state import format_connector_auth_widget

_SERVICE_LABELS: dict[str, str] = {
    "google-drive": "Google Drive",
    "gmail": "Gmail",
    "github": "GitHub",
    "slack": "Slack",
    "notion": "Notion",
    "airtable": "Airtable",
}


def get_service_label(service: str) -> str:
    """Returns human-friendly label for a connector service."""
    return _SERVICE_LABELS.get(service.lower().strip(), service.capitalize())


def format_connection_not_active_observation(
    error: ConnectionNotActiveError,
    auth_url: str = "",
    connection_id: str = "",
) -> Observation:
    """Translates a ConnectionNotActiveError into a structured Observation with widget syntax."""
    app_label = get_service_label(error.service)
    widget = format_connector_auth_widget(
        app_name=app_label,
        auth_url=auth_url,
        connection_id=connection_id,
    )
    text = (
        f"服务 {app_label} 当前尚未连接授权。\n\n"
        f"{widget}\n\n"
        f"请通过上方卡片完成授权连接。"
    )
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        error="SERVICE_NOT_CONNECTED",
        payload={
            "service": error.service,
            "connected": False,
            "widget": widget,
            "text": text,
            "auth_url": auth_url,
            "connection_id": connection_id,
        },
    )
