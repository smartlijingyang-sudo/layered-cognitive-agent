"""HTTP client for /api/device/*.  Layer0 never imports webserver transport."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from lca.infrastructure.tools.lca_computer.manifest import LOCAL_SYSTEM_ID as _COMPUTER_IDENTIFIER


@dataclass(frozen=True)
class DeviceToolCallResult:
    success: bool
    content: str = ""
    state: Any = None
    error: str = ""


class KernelServeHttpClient:
    """Aligns with LobeHub ``GatewayHttpClient`` (legacy alias)."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        token_type: str = "serviceToken",  # noqa: S107
    ) -> None:
        self._base = base_url.rstrip("/") + "/"
        self._token = token
        self._token_type = token_type

    async def query_device_status(self, user_id: str) -> dict[str, Any]:
        del user_id
        return await self._post("api/device/status", {})

    async def query_device_list(self, user_id: str) -> list[dict[str, Any]]:
        del user_id
        body = await self._post("api/device/devices", {})
        devices = body.get("devices")
        return devices if isinstance(devices, list) else []

    async def execute_tool_call(
        self,
        *,
        device_id: str,
        api_name: str,
        arguments: dict[str, Any],
        identifier: str = _COMPUTER_IDENTIFIER,
        timeout_s: float = 60,
    ) -> DeviceToolCallResult:
        body = await self._post(
            "api/device/tool-call",
            {
                "deviceId": device_id,
                "apiName": api_name,
                "identifier": identifier,
                "arguments": arguments,
                "timeout_s": timeout_s,
            },
        )
        return DeviceToolCallResult(
            success=bool(body.get("success", False)),
            content=str(body.get("content") or ""),
            state=body.get("state"),
            error=str(body.get("error") or ""),
        )

    async def invoke_rpc(
        self, *, device_id: str, method: str, params: Any = None
    ) -> dict[str, Any]:
        return await self._post(
            "api/device/rpc",
            {"deviceId": device_id, "method": method, "params": params},
        )

    async def upload_files(
        self,
        *,
        device_id: str,
        files: dict[str, Any],
        base_dir: str,
    ) -> DeviceToolCallResult:
        body = await self._post(
            "api/device/files/upload",
            {"deviceId": device_id, "files": files, "baseDir": base_dir},
        )
        return DeviceToolCallResult(
            success=bool(body.get("success", False)),
            content=str(body.get("content") or ""),
            error=str(body.get("error") or ""),
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        if self._token:
            body.setdefault("token", self._token)
            body.setdefault("tokenType", self._token_type)
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(urljoin(self._base, path), json=body)
            data = response.json()
            return (
                data if isinstance(data, dict) else {"success": False, "error": "invalid response"}
            )
