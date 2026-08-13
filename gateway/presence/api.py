"""GET /presence/devices — list Presence records."""

from __future__ import annotations

from typing import cast

from starlette.requests import Request
from starlette.responses import JSONResponse

from gateway.cors import cors_headers
from gateway.presence.registry import PresenceRegistry


def _presence_of(request: Request) -> PresenceRegistry:
    return cast("PresenceRegistry", request.app.state.presence)


async def list_devices(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    devices = [d.as_dict() for d in _presence_of(request).list_devices()]
    return JSONResponse({"devices": devices}, headers=cors_headers())
