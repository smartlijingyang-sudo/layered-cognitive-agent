"""Load Composio settings from process env (CLI / one-off scripts).

Profile-injected plugins must not read ``os.environ`` directly; this module is
for operator tooling that runs outside the plugin boot path.
"""

from __future__ import annotations

import json
import os

from lca.infrastructure.integrations.composio.settings import ComposioSettings
from lca.infrastructure.llm_adapter.factory import load_dotenv_if_present


def load_composio_settings_from_env(*, dotenv_path: str | None = None) -> ComposioSettings:
    """Build :class:`ComposioSettings` after loading ``.env`` from the repo."""
    load_dotenv_if_present(dotenv_path)
    api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("COMPOSIO_API_KEY is required — set it in .env")
    return ComposioSettings.from_plugin_config(
        api_key=api_key,
        callback_url=os.environ.get("LCA_COMPOSIO_CALLBACK_URL"),
        default_user_id=os.environ.get("LCA_COMPOSIO_USER_ID"),
        auth_config_ids=os.environ.get("COMPOSIO_AUTH_CONFIG_IDS"),
        connections_path=os.environ.get("LCA_COMPOSIO_CONNECTIONS_PATH"),
    )


def connection_to_public_dict(conn: object) -> dict[str, object]:
    """Serialize a connection for CLI / HTTP consumers."""
    from lca.infrastructure.integrations.composio.models import ComposioConnection

    if not isinstance(conn, ComposioConnection):
        raise TypeError(f"expected ComposioConnection, got {type(conn).__name__}")
    return {
        "identifier": conn.identifier,
        "label": conn.label,
        "app_slug": conn.app_slug,
        "connected_account_id": conn.connected_account_id,
        "auth_config_id": conn.auth_config_id,
        "user_id": conn.user_id,
        "status": conn.status,
        "connected": conn.is_active,
        "redirect_url": conn.redirect_url,
        "tool_count": len(conn.tools),
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in conn.tools
        ],
    }


def connection_to_lobehub_plugin(conn: object) -> dict[str, object]:
    """Shape compatible with LobeHub ``useFetchUserComposioConnections`` mapping."""
    from lca.infrastructure.integrations.composio.models import ComposioConnection

    if not isinstance(conn, ComposioConnection):
        raise TypeError(f"expected ComposioConnection, got {type(conn).__name__}")
    return {
        "identifier": conn.identifier,
        "type": "plugin",
        "source": "composio",
        "customParams": {
            "composio": {
                "appSlug": conn.app_slug,
                "authConfigId": conn.auth_config_id,
                "connectedAccountId": conn.connected_account_id,
                "linkedByUserId": conn.user_id,
                "redirectUrl": conn.redirect_url,
                "status": conn.status,
            }
        },
        "manifest": {
            "identifier": conn.identifier,
            "type": "default",
            "api": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema or {"type": "object", "properties": {}},
                }
                for tool in conn.tools
            ],
            "meta": {
                "avatar": "🔌",
                "title": conn.label,
                "description": f"Composio: {conn.label}",
            },
        },
    }


def parse_auth_config_ids(raw: str) -> dict[str, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v}
