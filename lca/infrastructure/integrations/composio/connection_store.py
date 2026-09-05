"""File-backed Composio connection store (LCA SSOT for OAuth links)."""

from __future__ import annotations

import json
from pathlib import Path

from lca.infrastructure.integrations.composio.models import ComposioConnection, ComposioToolDef


class ComposioConnectionStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load_all(self) -> list[ComposioConnection]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        rows = raw.get("connections") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return []
        out: list[ComposioConnection] = []
        for row in rows:
            conn = _decode_connection(row)
            if conn is not None:
                out.append(conn)
        return out

    def get(self, identifier: str) -> ComposioConnection | None:
        for conn in self.load_all():
            if conn.identifier == identifier:
                return conn
        return None

    def upsert(self, connection: ComposioConnection) -> None:
        rows = [c for c in self.load_all() if c.identifier != connection.identifier]
        rows.append(connection)
        self._write(rows)

    def delete(self, identifier: str) -> None:
        rows = [c for c in self.load_all() if c.identifier != identifier]
        self._write(rows)

    def _write(self, rows: list[ComposioConnection]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"connections": [_encode_connection(row) for row in rows]}
        self._path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _encode_connection(conn: ComposioConnection) -> dict[str, object]:
    return {
        "identifier": conn.identifier,
        "app_slug": conn.app_slug,
        "label": conn.label,
        "connected_account_id": conn.connected_account_id,
        "auth_config_id": conn.auth_config_id,
        "user_id": conn.user_id,
        "status": conn.status,
        "redirect_url": conn.redirect_url,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in conn.tools
        ],
    }


def _decode_connection(row: object) -> ComposioConnection | None:
    if not isinstance(row, dict):
        return None
    identifier = str(row.get("identifier") or "").strip()
    connected_account_id = str(row.get("connected_account_id") or "").strip()
    if not identifier or not connected_account_id:
        return None
    tools_raw = row.get("tools") or []
    tools: list[ComposioToolDef] = []
    if isinstance(tools_raw, list):
        for item in tools_raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            schema = item.get("input_schema")
            tools.append(
                ComposioToolDef(
                    name=name,
                    description=str(item.get("description") or ""),
                    input_schema=schema if isinstance(schema, dict) else {},
                )
            )
    return ComposioConnection(
        identifier=identifier,
        app_slug=str(row.get("app_slug") or ""),
        label=str(row.get("label") or identifier),
        connected_account_id=connected_account_id,
        auth_config_id=str(row.get("auth_config_id") or ""),
        user_id=str(row.get("user_id") or ""),
        status=str(row.get("status") or "PENDING"),
        redirect_url=str(row["redirect_url"]) if row.get("redirect_url") else None,
        tools=tools,
    )
