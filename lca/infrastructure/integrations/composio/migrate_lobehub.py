"""One-time migration of Composio connections from LobeHub Postgres."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from lca.infrastructure.integrations.composio.catalog import get_app_by_identifier
from lca.infrastructure.integrations.composio.models import ComposioConnection, ComposioToolDef
from lca.infrastructure.integrations.composio.service import ComposioIntegration


@dataclass(frozen=True, slots=True)
class MigrationResult:
    imported: int
    skipped: int
    identifiers: tuple[str, ...]


def row_to_connection(row: dict[str, Any]) -> ComposioConnection | None:
    """Convert a LobeHub plugin or connector row into LCA SSOT."""
    identifier = str(row.get("identifier") or "").strip()
    composio = _extract_composio_params(row)
    if not identifier or composio is None:
        return None

    connected_account_id = str(composio.get("connectedAccountId") or composio.get("connected_account_id") or "").strip()
    if not connected_account_id:
        return None

    app_slug = str(composio.get("appSlug") or composio.get("app_slug") or "").strip()
    app = get_app_by_identifier(identifier)
    if app is not None and not app_slug:
        app_slug = app.app_slug
    label = str(row.get("label") or (app.label if app else identifier))

    tools = _tools_from_manifest(row.get("manifest"))
    status = str(composio.get("status") or "PENDING").upper()
    user_id = str(
        composio.get("linkedByUserId")
        or composio.get("linked_by_user_id")
        or row.get("user_id")
        or ""
    ).strip()

    return ComposioConnection(
        identifier=identifier,
        app_slug=app_slug,
        label=label,
        connected_account_id=connected_account_id,
        auth_config_id=str(composio.get("authConfigId") or composio.get("auth_config_id") or ""),
        user_id=user_id,
        status=status,
        redirect_url=_optional_str(composio.get("redirectUrl") or composio.get("redirect_url")),
        tools=tools,
    )


def migrate_rows(integration: ComposioIntegration, rows: list[dict[str, Any]]) -> MigrationResult:
    imported = 0
    skipped = 0
    identifiers: list[str] = []
    for row in rows:
        conn = row_to_connection(row)
        if conn is None:
            skipped += 1
            continue
        existing = integration.get_connection(conn.identifier)
        if existing is not None and existing.is_active:
            skipped += 1
            continue
        if integration.import_connection(conn):
            imported += 1
            identifiers.append(conn.identifier)
        else:
            skipped += 1
    return MigrationResult(imported=imported, skipped=skipped, identifiers=tuple(identifiers))


def fetch_lobehub_rows(database_url: str) -> list[dict[str, Any]]:
    """Read Composio rows from LobeHub Postgres (plugins + connectors)."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "DB migration requires psycopg. Install with: uv add psycopg[binary]"
        ) from exc

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError(f"unsupported DATABASE_URL scheme: {parsed.scheme!r}")

    rows: list[dict[str, Any]] = []
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT identifier, custom_params, manifest, user_id
                FROM user_installed_plugins
                WHERE custom_params ? 'composio'
                """
        )
        for identifier, custom_params, manifest, user_id in cur.fetchall():
            rows.append(
                {
                    "identifier": identifier,
                    "custom_params": _json_dict(custom_params),
                    "manifest": _json_dict(manifest),
                    "user_id": user_id,
                }
            )

        cur.execute(
            """
                SELECT identifier, metadata, name, user_id
                FROM user_connectors
                WHERE metadata ? 'composio'
                  AND agent_id IS NULL
                """
        )
        for identifier, metadata, name, user_id in cur.fetchall():
            meta = _json_dict(metadata)
            composio = meta.get("composio")
            if not isinstance(composio, dict):
                continue
            rows.append(
                {
                    "identifier": identifier,
                    "custom_params": {"composio": composio},
                    "manifest": None,
                    "label": name,
                    "user_id": user_id,
                }
            )
    return _dedupe_rows(rows)


def load_rows_from_json(path: str) -> list[dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("rows"), list):
        return [item for item in raw["rows"] if isinstance(item, dict)]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    raise ValueError("JSON input must be a list of rows or {\"rows\": [...]}")


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        identifier = str(row.get("identifier") or "").strip()
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        out.append(row)
    return out


def _extract_composio_params(row: dict[str, Any]) -> dict[str, Any] | None:
    custom = row.get("custom_params") or row.get("customParams") or {}
    if not isinstance(custom, dict):
        return None
    composio = custom.get("composio")
    return composio if isinstance(composio, dict) else None


def _tools_from_manifest(manifest: Any) -> list[ComposioToolDef]:
    if not isinstance(manifest, dict):
        return []
    api = manifest.get("api")
    if not isinstance(api, list):
        return []
    tools: list[ComposioToolDef] = []
    for item in api:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        schema = item.get("parameters") or item.get("input_schema") or item.get("inputSchema")
        tools.append(
            ComposioToolDef(
                name=name,
                description=str(item.get("description") or ""),
                input_schema=schema if isinstance(schema, dict) else {},
            )
        )
    return tools


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _optional_str(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
