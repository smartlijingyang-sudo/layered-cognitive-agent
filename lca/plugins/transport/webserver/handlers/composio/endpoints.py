"""HTTP handlers for LCA-native Composio connection management."""

from __future__ import annotations

import contextlib
import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from lca.infrastructure.integrations.composio.env_settings import (
    connection_to_lobehub_plugin,
    connection_to_public_dict,
)
from lca.infrastructure.integrations.composio.oauth_callback import oauth_callback_html
from lca.infrastructure.integrations.composio.service import ComposioIntegration
from lca.plugins.transport.webserver.handlers.cors import cors_headers

_bound: ComposioIntegration | None = None


def bind_composio(integration: ComposioIntegration) -> None:
    global _bound
    _bound = integration


def _integration() -> ComposioIntegration:
    if _bound is None:
        raise RuntimeError("composio integration is not bound")
    return _bound


async def oauth_callback(request: Request) -> Response:
    params = request.query_params
    status = params.get("status")
    oauth_error = params.get("error")
    connected_account_id = params.get("connected_account_id") or params.get("connectedAccountId")
    success = not oauth_error and (status or "").lower() != "failed"

    if success:
        await _integration().handle_oauth_callback(
            connected_account_id=connected_account_id,
            status=status,
            oauth_error=oauth_error,
        )
    return oauth_callback_html(success=success)


async def list_connections(_request: Request) -> JSONResponse:
    rows = [connection_to_lobehub_plugin(conn) for conn in _integration().list_connections()]
    return JSONResponse({"connections": rows, "plugins": rows}, headers=cors_headers())


async def create_connection(request: Request) -> JSONResponse:
    body = await _read_json(request)
    identifier = str(body.get("identifier") or body.get("service") or "").strip()
    if not identifier:
        return _error("identifier is required", status_code=400)

    app_slug = str(body.get("appSlug") or body.get("app_slug") or "").strip() or None
    label = str(body.get("label") or "").strip() or None
    user_id = str(body.get("userId") or body.get("user_id") or "").strip() or None

    existing = _integration().get_connection(identifier)
    if existing and existing.is_active:
        payload = connection_to_public_dict(existing)
        return JSONResponse(payload, headers=cors_headers())

    if app_slug and label:
        from lca.infrastructure.integrations.composio.catalog import get_app_by_identifier

        if get_app_by_identifier(identifier) is None:
            return _error(f"unknown Composio service identifier: {identifier}", status_code=400)

    conn = await _integration().create_connection(identifier, user_id=user_id)
    payload = {
        "authConfigId": conn.auth_config_id,
        "connectedAccountId": conn.connected_account_id,
        "identifier": conn.identifier,
        "redirectUrl": conn.redirect_url,
        **connection_to_public_dict(conn),
    }
    return JSONResponse(payload, headers=cors_headers())


async def get_connection(request: Request) -> JSONResponse:
    connected_account_id = str(request.path_params.get("connected_account_id") or "").strip()
    conn = _integration().get_connection_by_account_id(connected_account_id)
    if conn is None:
        return _error("connection not found", status_code=404)

    if conn.is_active:
        return JSONResponse(
            {
                "appSlug": conn.app_slug,
                "status": "ACTIVE",
                "connectedAccountId": conn.connected_account_id,
            },
            headers=cors_headers(),
        )

    account = await _integration()._client.get_connected_account(conn.connected_account_id)
    status = str(account.get("status") or conn.status).upper()
    if status == "FAILED":
        return JSONResponse(
            {"appSlug": conn.app_slug, "status": status, "error": "AUTH_ERROR"},
            headers=cors_headers(),
        )
    return JSONResponse(
        {"appSlug": conn.app_slug, "status": status, "connectedAccountId": conn.connected_account_id},
        headers=cors_headers(),
    )


async def refresh_connection(request: Request) -> JSONResponse:
    identifier = str(request.path_params.get("identifier") or "").strip()
    if not identifier:
        return _error("identifier is required", status_code=400)
    try:
        conn = await _integration().refresh_connection(identifier)
    except ValueError as exc:
        return _error(str(exc), status_code=404)
    return JSONResponse(connection_to_public_dict(conn), headers=cors_headers())


async def delete_connection(request: Request) -> JSONResponse:
    identifier = str(request.path_params.get("identifier") or "").strip()
    if not identifier:
        return _error("identifier is required", status_code=400)
    conn = _integration().get_connection(identifier)
    if conn is None:
        return JSONResponse({"success": True}, headers=cors_headers())
    with contextlib.suppress(Exception):
        await _integration()._client.delete_connected_account(conn.connected_account_id)
    _integration().delete_connection(identifier)
    return JSONResponse({"success": True}, headers=cors_headers())


async def composio_options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=cors_headers())


async def connections(request: Request) -> JSONResponse | Response:
    if request.method == "OPTIONS":
        return await composio_options(request)
    if request.method == "GET":
        return await list_connections(request)
    if request.method == "POST":
        return await create_connection(request)
    return JSONResponse({"error": "method not allowed"}, status_code=405, headers=cors_headers())


async def connection_by_account(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return await composio_options(request)
    return await get_connection(request)


async def connection_by_identifier(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return await composio_options(request)
    if request.method == "DELETE":
        return await delete_connection(request)
    return JSONResponse({"error": "method not allowed"}, status_code=405, headers=cors_headers())


async def connection_refresh(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return await composio_options(request)
    return await refresh_connection(request)


async def _read_json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return {}
    return body if isinstance(body, dict) else {}


def _error(message: str, *, status_code: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code, headers=cors_headers())
