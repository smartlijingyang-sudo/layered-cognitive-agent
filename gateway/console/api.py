"""POST /console/sessions — open a PTY on an online host."""

from __future__ import annotations

import json
from typing import cast

from starlette.requests import Request
from starlette.responses import JSONResponse

from gateway.console.sessions import CapabilityMissingError, ConsoleBook, DeviceOfflineError
from gateway.cors import cors_headers
from gateway.presence.registry import PresenceRegistry


def _presence_of(request: Request) -> PresenceRegistry:
    return cast("PresenceRegistry", request.app.state.presence)


def _consoles_of(request: Request) -> ConsoleBook:
    return cast("ConsoleBook", request.app.state.consoles)


async def create_session(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400, headers=cors_headers())
    if not isinstance(body, dict):
        return JSONResponse(
            {"error": "request body must be a JSON object"},
            status_code=400,
            headers=cors_headers(),
        )
    device_id = str(body.get("device_id") or "").strip()
    if not device_id:
        return JSONResponse(
            {"error": "device_id is required"}, status_code=400, headers=cors_headers()
        )
    cols = int(body.get("cols") or 80)
    rows = int(body.get("rows") or 24)
    try:
        session = await _consoles_of(request).open(
            _presence_of(request), device_id, cols=cols, rows=rows
        )
    except DeviceOfflineError:
        return JSONResponse({"error": "device offline"}, status_code=409, headers=cors_headers())
    except CapabilityMissingError:
        return JSONResponse(
            {"error": "device has no console capability"},
            status_code=409,
            headers=cors_headers(),
        )
    return JSONResponse(
        {
            "session_id": session.session_id,
            "device_id": session.device_id,
            "attach_url": f"/console/sessions/{session.session_id}",
        },
        status_code=201,
        headers=cors_headers(),
    )
