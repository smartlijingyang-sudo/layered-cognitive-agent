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
    """Translates a ConnectionNotActiveError into a structured Observation with widget syntax (Zero Model URL Exposure)."""
    from lca.infrastructure.connectors.core.intent_vault import get_default_intent_vault

    app_label = get_service_label(error.service)
    intent_id = ""
    if auth_url:
        vault = get_default_intent_vault()
        intent_id = vault.create_intent(
            service=error.service,
            app_name=app_label,
            auth_url=auth_url,
            connection_id=connection_id,
            user_id=error.user_id,
        )

    widget = format_connector_auth_widget(
        app_name=app_label,
        intent_id=intent_id if intent_id else None,
        auth_url="" if intent_id else auth_url,
        connection_id=connection_id,
    )
    text = (
        f"服务 {app_label} 当前尚未连接授权。你在回复中必须原样输出以下卡片挂载标签：\n\n"
        f"{widget}\n\n"
        f"严禁在回复中输出裸 URL 或假链接，前端会自动将上述标签渲染为交互式授权卡片。"
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
            "intent_id": intent_id,
            "connection_id": connection_id,
            "display_instruction": (
                f"服务 {app_label} 授权卡片门票已就绪。在最终回复中你必须原样包含挂载标签 '{widget}'，"
                "严禁输出裸 URL 或脑补链接。"
            ),
        },
    )
