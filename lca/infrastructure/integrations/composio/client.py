"""Thin httpx client for Composio REST API v3."""

from __future__ import annotations

from typing import Any

import httpx

from lca.infrastructure.integrations.composio.settings import ComposioSettings


class ComposioApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ComposioHttpClient:
    def __init__(self, settings: ComposioSettings) -> None:
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._settings.api_key, "Content-Type": "application/json"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._settings.base_url}{path}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
            )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise ComposioApiError(
                f"Composio {method} {path} failed ({response.status_code}): {detail}",
                status_code=response.status_code,
            )
        if not response.content:
            return {}
        data = response.json()
        return data

    async def list_auth_configs(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/auth_configs")
        items = data.get("items") if isinstance(data, dict) else data
        return list(items or [])

    async def create_auth_config(self, app_slug: str) -> dict[str, Any]:
        payload = {"toolkit": {"slug": app_slug}, "auth_scheme": "OAUTH2", "type": "use_composio_managed_auth"}
        data = await self._request("POST", "/auth_configs", json_body=payload)
        return data if isinstance(data, dict) else {}

    async def link_connected_account(
        self,
        *,
        user_id: str,
        auth_config_id: str,
        callback_url: str,
        allow_multiple: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "user_id": user_id,
            "auth_config_id": auth_config_id,
            "callback_url": callback_url,
        }
        if allow_multiple:
            body["allow_multiple"] = True
        data = await self._request("POST", "/connected_accounts/link", json_body=body)
        return data if isinstance(data, dict) else {}

    async def get_connected_account(self, connected_account_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/connected_accounts/{connected_account_id}")
        return data if isinstance(data, dict) else {}

    async def delete_connected_account(self, connected_account_id: str) -> None:
        await self._request("DELETE", f"/connected_accounts/{connected_account_id}")

    async def list_tools(self, app_slug: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/tools",
            params={"toolkit_slug": app_slug, "limit": 1000},
        )
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    async def execute_tool(
        self,
        *,
        tool_slug: str,
        connected_account_id: str,
        user_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        body = {
            "connected_account_id": connected_account_id,
            "user_id": user_id,
            "arguments": arguments or {},
            "version": "00000000_00",
        }
        data = await self._request("POST", f"/tools/execute/{tool_slug}", json_body=body)
        if isinstance(data, dict):
            return data.get("data", data.get("result", data))
        return data
