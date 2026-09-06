"""Composio integration service — emit composio.* spine events at SSOT boundaries."""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.observability.closure.composio_ep_closure import (
    COMPOSIO_CONNECTION_ACTIVATED,
    COMPOSIO_CONNECTION_CREATED,
    COMPOSIO_CONNECTION_DELETED,
    COMPOSIO_CONNECTION_PENDING,
    COMPOSIO_CONNECTION_REFRESHED,
    COMPOSIO_OAUTH_CALLBACK_FAILED,
    COMPOSIO_OAUTH_CALLBACK_PROCESSED,
    COMPOSIO_OAUTH_CALLBACK_RECEIVED,
    COMPOSIO_TOOL_EXECUTED,
    COMPOSIO_TOOL_EXECUTION_FAILED,
    COMPOSIO_TOOL_EXECUTION_STARTED,
)
from lca.infrastructure.integrations.composio.catalog.catalog import get_app_by_identifier
from lca.infrastructure.integrations.composio.client.client import ComposioHttpClient
from lca.infrastructure.integrations.composio.connection.connection_store import ComposioConnectionStore
from lca.infrastructure.integrations.composio.models.models import ComposioConnection, ComposioToolDef
from lca.infrastructure.integrations.composio.settings.settings import ComposioSettings


def _emit_composio(execution_point: str, payload: dict[str, Any]) -> None:
    from lca.infrastructure.observability.domain_event_publish import (
        publish_structural_event,
    )

    publish_structural_event(
        execution_point=execution_point,
        channel="fact",
        payload=payload,
        producer=type(None),
    )


def _connection_payload(conn: ComposioConnection, **extra: Any) -> dict[str, Any]:
    base = {
        "identifier": conn.identifier,
        "app_slug": conn.app_slug,
        "status": conn.status,
        "connected_account_id": conn.connected_account_id,
        "user_id": conn.user_id,
    }
    base.update(extra)
    return base


def _tool_defs_from_api(items: list[dict[str, Any]]) -> list[ComposioToolDef]:
    out: list[ComposioToolDef] = []
    for item in items:
        name = str(item.get("slug") or item.get("name") or "").strip()
        if not name:
            continue
        schema = item.get("inputParameters") or item.get("input_schema") or item.get("parameters")
        out.append(
            ComposioToolDef(
                name=name,
                description=str(item.get("description") or ""),
                input_schema=schema if isinstance(schema, dict) else {"type": "object", "properties": {}},
            )
        )
    return out


class ComposioIntegration:
    """LCA-native Composio runtime — connection SSOT is the local connection store."""

    def __init__(self, settings: ComposioSettings) -> None:
        self._settings = settings
        self._client = ComposioHttpClient(settings)
        self._store = ComposioConnectionStore(settings.connections_path)

    @property
    def settings(self) -> ComposioSettings:
        return self._settings

    def list_connections(self) -> list[ComposioConnection]:
        return self._store.load_all()

    def list_active_connections(self) -> list[ComposioConnection]:
        return [c for c in self.list_connections() if c.is_active and c.tools]

    def get_connection(self, identifier: str) -> ComposioConnection | None:
        return self._store.get(identifier)

    def get_connection_by_account_id(self, connected_account_id: str) -> ComposioConnection | None:
        needle = connected_account_id.strip()
        if not needle:
            return None
        for conn in self.list_connections():
            if conn.connected_account_id == needle:
                return conn
        return None

    async def resolve_auth_config_id(self, identifier: str, app_slug: str) -> str:
        pinned = self._settings.auth_config_ids.get(identifier)
        if pinned:
            return pinned
        configs = await self._client.list_auth_configs()
        for cfg in configs:
            toolkit = cfg.get("toolkit") if isinstance(cfg.get("toolkit"), dict) else {}
            slug = str(toolkit.get("slug") or "").upper()
            if slug == app_slug.upper() and cfg.get("id"):
                return str(cfg["id"])
        created = await self._client.create_auth_config(app_slug)
        auth_id = str(created.get("id") or "")
        if not auth_id:
            raise RuntimeError(f"Failed to resolve Composio auth config for {app_slug}")
        return auth_id

    async def create_connection(self, identifier: str, *, user_id: str | None = None) -> ComposioConnection:
        app = get_app_by_identifier(identifier)
        if app is None:
            raise ValueError(f"Unknown Composio service identifier: {identifier}")

        owner = (user_id or self._settings.default_user_id).strip()
        auth_config_id = await self.resolve_auth_config_id(identifier, app.app_slug)
        link = await self._client.link_connected_account(
            user_id=owner,
            auth_config_id=auth_config_id,
            callback_url=self._settings.callback_url,
        )
        connected_account_id = str(link.get("id") or link.get("connected_account_id") or "").strip()
        if not connected_account_id:
            raise RuntimeError(f"Composio link returned no connected account id for {identifier}")

        tools: list[ComposioToolDef] = []
        try:
            tools = _tool_defs_from_api(await self._client.list_tools(app.app_slug))
        except Exception:
            tools = []

        conn = ComposioConnection(
            identifier=identifier,
            app_slug=app.app_slug,
            label=app.label,
            connected_account_id=connected_account_id,
            auth_config_id=auth_config_id,
            user_id=owner,
            status="PENDING",
            redirect_url=str(link.get("redirect_url") or link.get("redirectUrl") or "") or None,
            tools=tools,
        )
        self._store.upsert(conn)
        _emit_composio(COMPOSIO_CONNECTION_CREATED, _connection_payload(conn))
        if conn.redirect_url:
            _emit_composio(
                COMPOSIO_CONNECTION_PENDING,
                {**_connection_payload(conn), "redirect_url": conn.redirect_url},
            )
        return conn

    async def handle_oauth_callback(
        self,
        *,
        connected_account_id: str | None = None,
        status: str | None = None,
        oauth_error: str | None = None,
    ) -> list[ComposioConnection]:
        """Refresh pending connection(s) after Composio OAuth redirect."""
        _emit_composio(
            COMPOSIO_OAUTH_CALLBACK_RECEIVED,
            {
                "connected_account_id": connected_account_id or "",
                "status": status or "",
                "oauth_error": oauth_error or "",
            },
        )
        success = not oauth_error and (status or "").lower() != "failed"
        if not success:
            _emit_composio(
                COMPOSIO_OAUTH_CALLBACK_FAILED,
                {
                    "connected_account_id": connected_account_id or "",
                    "status": status or "",
                    "oauth_error": oauth_error or "",
                },
            )
            return []

        refreshed: list[ComposioConnection] = []
        account_id = (connected_account_id or "").strip()
        if account_id:
            conn = self.get_connection_by_account_id(account_id)
            if conn is not None:
                refreshed.append(await self.refresh_connection(conn.identifier))
            _emit_composio(
                COMPOSIO_OAUTH_CALLBACK_PROCESSED,
                {"connected_account_id": account_id, "refreshed_count": len(refreshed)},
            )
            return refreshed

        for conn in self.list_connections():
            if conn.status.upper() == "PENDING":
                refreshed.append(await self.refresh_connection(conn.identifier))
        _emit_composio(
            COMPOSIO_OAUTH_CALLBACK_PROCESSED,
            {"connected_account_id": "", "refreshed_count": len(refreshed)},
        )
        return refreshed

    async def refresh_connection(self, identifier: str) -> ComposioConnection:
        conn = self._store.get(identifier)
        if conn is None:
            raise ValueError(f"No Composio connection for {identifier}")

        account = await self._client.get_connected_account(conn.connected_account_id)
        status = str(account.get("status") or "PENDING").upper()
        tools = conn.tools
        if status == "ACTIVE":
            tools = _tool_defs_from_api(await self._client.list_tools(conn.app_slug))

        updated = ComposioConnection(
            identifier=conn.identifier,
            app_slug=conn.app_slug,
            label=conn.label,
            connected_account_id=conn.connected_account_id,
            auth_config_id=conn.auth_config_id,
            user_id=conn.user_id,
            status=status,
            redirect_url=None if status == "ACTIVE" else conn.redirect_url,
            tools=tools,
        )
        self._store.upsert(updated)
        _emit_composio(COMPOSIO_CONNECTION_REFRESHED, _connection_payload(updated))
        if status == "ACTIVE":
            _emit_composio(
                COMPOSIO_CONNECTION_ACTIVATED,
                {**_connection_payload(updated), "tool_count": len(tools)},
            )
        return updated

    async def execute_action(
        self,
        identifier: str,
        tool_slug: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        conn = self._store.get(identifier)
        if conn is None or not conn.is_active:
            _emit_composio(
                COMPOSIO_TOOL_EXECUTION_FAILED,
                {
                    "identifier": identifier,
                    "tool_slug": tool_slug,
                    "reason": "not_connected",
                },
            )
            raise RuntimeError(
                f"Composio service {identifier!r} is not connected. "
                f"Call composioConnect first."
            )
        _emit_composio(
            COMPOSIO_TOOL_EXECUTION_STARTED,
            {"identifier": identifier, "tool_slug": tool_slug},
        )
        try:
            result = await self._client.execute_tool(
                tool_slug=tool_slug,
                connected_account_id=conn.connected_account_id,
                user_id=conn.user_id,
                arguments=arguments,
            )
        except Exception as exc:
            _emit_composio(
                COMPOSIO_TOOL_EXECUTION_FAILED,
                {
                    "identifier": identifier,
                    "tool_slug": tool_slug,
                    "reason": type(exc).__name__,
                    "error": str(exc)[:500],
                },
            )
            raise
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        _emit_composio(
            COMPOSIO_TOOL_EXECUTED,
            {
                "identifier": identifier,
                "tool_slug": tool_slug,
                "result_chars": len(text),
            },
        )
        return text

    def delete_connection(self, identifier: str) -> None:
        self._store.delete(identifier)
        _emit_composio(COMPOSIO_CONNECTION_DELETED, {"identifier": identifier})

    def import_connection(self, connection: ComposioConnection, *, overwrite: bool = False) -> bool:
        """Import a connection row (migration/bootstrap). Returns True when written."""
        existing = self.get_connection(connection.identifier)
        if existing is not None and existing.is_active and not overwrite:
            return False
        self._store.upsert(connection)
        _emit_composio(COMPOSIO_CONNECTION_CREATED, _connection_payload(connection, imported=True))
        return True
