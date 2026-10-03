"""Composio settings — values arrive from Profile plugin config, not os.environ reads in plugins."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from lca.infrastructure.path import expand_user_path, get_lca_home

_DEFAULT_BASE_URL = "https://backend.composio.dev/api/v3"
_DEFAULT_CALLBACK_URL = "http://10.36.6.252:8765/composio/oauth/callback"
_DEFAULT_USER_ID = "lca-local-user"


def resolve_user_connections_path(
    user_id: str = _DEFAULT_USER_ID,
    lca_home: Path | None = None,
) -> Path:
    home = lca_home or get_lca_home()
    return home / "users" / user_id / "connectors" / "connections.json"


def _default_connections_path(user_id: str = _DEFAULT_USER_ID) -> Path:
    return resolve_user_connections_path(user_id)


@dataclass(frozen=True, slots=True)
class ComposioSettings:
    api_key: str
    base_url: str = _DEFAULT_BASE_URL
    callback_url: str = _DEFAULT_CALLBACK_URL
    default_user_id: str = _DEFAULT_USER_ID
    auth_config_ids: dict[str, str] = field(default_factory=dict)
    connections_path: Path = field(default_factory=_default_connections_path)

    @classmethod
    def from_plugin_config(
        cls,
        *,
        api_key: str,
        base_url: str | None = None,
        callback_url: str | None = None,
        default_user_id: str | None = None,
        auth_config_ids: str | dict[str, str] | None = None,
        connections_path: str | None = None,
    ) -> ComposioSettings:
        parsed_auth: dict[str, str] = {}
        if isinstance(auth_config_ids, dict):
            parsed_auth = {str(k): str(v) for k, v in auth_config_ids.items()}
        elif isinstance(auth_config_ids, str) and auth_config_ids.strip():
            parsed_auth = _parse_auth_config_ids(auth_config_ids)

        owner = (default_user_id or _DEFAULT_USER_ID).strip()
        path = (
            expand_user_path(connections_path)
            if connections_path
            else resolve_user_connections_path(owner)
        )
        return cls(
            api_key=api_key.strip(),
            base_url=(base_url or _DEFAULT_BASE_URL).rstrip("/"),
            callback_url=callback_url or _DEFAULT_CALLBACK_URL,
            default_user_id=owner,
            auth_config_ids=parsed_auth,
            connections_path=path,
        )


def _parse_auth_config_ids(raw: str) -> dict[str, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v}
