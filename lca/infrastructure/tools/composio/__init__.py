"""Composio LLM tools — connect + dynamic actions from active connections."""

from __future__ import annotations

from typing import Any, cast

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.infrastructure.connectors.core.state import format_connector_auth_widget
from lca.infrastructure.integrations.composio import get_app_by_identifier
from lca.infrastructure.integrations.composio.service.service import ComposioIntegration
from lca.infrastructure.tools.builder.builder import build_tools_from_manifest

IDENTIFIER = "composio"

MANAGEMENT_MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="composioConnect",
            description=(
                "Connect a Composio-managed third-party service via OAuth "
                "(e.g. google-drive, gmail, slack). Emits an interactive [widget:connector_auth?...] "
                "ticket for user authorization. In your final response to the user, you MUST include "
                "the exact [widget:connector_auth?...] tag verbatim so the frontend renders the "
                "interactive authorization card. DO NOT print raw authorization URLs or markdown links."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Composio service identifier, e.g. google-drive",
                    }
                },
                "required": ["service"],
            },
            is_idempotent=False,
            namespace="ext",
        ),
        ToolApi(
            name="composioRefresh",
            description=(
                "Refresh Composio connection status after the user completed OAuth. "
                "Call after the user authorizes via the redirect URL."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Composio service identifier to refresh",
                    }
                },
                "required": ["service"],
            },
            is_idempotent=True,
            namespace="ext",
        ),
    ),
    meta=ToolMeta(
        avatar="🔗",
        title="Composio",
        description="Connect and use Composio third-party integrations",
    ),
)


class ComposioManagementExecutor:
    def __init__(self, integration: ComposioIntegration) -> None:
        self._integration = integration

    async def composioConnect(self, params: dict[str, Any]) -> Observation:  # noqa: N802
        service = str(params.get("service") or "").strip()
        if not service:
            return _validation_error("service is required")

        if get_app_by_identifier(service) is None:
            return _validation_error(f"Unknown Composio service: {service}")

        existing = self._integration.get_connection(service)
        if existing and existing.is_active:
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload={
                    "text": f"Already connected to {existing.label}.",
                    "identifier": service,
                    "connected": True,
                },
            )

        conn = await self._integration.create_connection(service)
        if conn.is_active:
            text = f"Connected to {conn.label}."
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload={"text": text, "identifier": service, "connected": True},
            )

        redirect = conn.redirect_url or ""
        conn_id = conn.connected_account_id or ""
        app_name = conn.label or service.capitalize()

        from lca.infrastructure.connectors.core.intent_vault import get_default_intent_vault

        intent_id = ""
        if redirect:
            user_id = getattr(self._integration, "user_id", None) or "default"
            vault = get_default_intent_vault()
            intent_id = vault.create_intent(
                service=service,
                app_name=app_name,
                auth_url=redirect,
                connection_id=conn_id,
                user_id=user_id,
            )

        # Fail-closed: 不再传递 auth_url 回退分支 —— create_intent 永不返回空，
        # intent 为空即无凭据，标签不带任何 URL（旧分支不可达，已删除）。
        widget = format_connector_auth_widget(
            app_name=app_name,
            intent_id=intent_id or None,
            connection_id=conn_id,
        )
        text = (
            f"服务 {app_name} 授权门票已就绪。你在最终回复中必须原样输出以下卡片挂载标签：\n\n"
            f"{widget}\n\n"
            "严禁在回复中输出裸 URL 或编造链接，前端会自动将上述标签渲染为交互式授权卡片。"
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "text": text,
                "identifier": service,
                "connected": False,
                "intent_id": intent_id,
                "widget_tag": widget,
                "display_instruction": (
                    f"服务 {app_name} 授权卡片门票已就绪。在最终回复中你必须原样包含挂载标签 '{widget}'，"
                    "严禁输出裸 URL 或脑补链接。"
                ),
            },
        )

    async def composioRefresh(self, params: dict[str, Any]) -> Observation:  # noqa: N802
        service = str(params.get("service") or "").strip()
        if not service:
            return _validation_error("service is required")
        conn = await self._integration.refresh_connection(service)
        if conn.is_active:
            text = f"{conn.label} is connected with {len(conn.tools)} tools available."
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload={
                    "text": text,
                    "identifier": service,
                    "connected": True,
                    "tool_count": len(conn.tools),
                },
            )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "text": f"{conn.label} is not active yet (status={conn.status}).",
                "identifier": service,
                "connected": False,
                "status": conn.status,
            },
        )


class ComposioActionExecutor:
    def __init__(self, integration: ComposioIntegration, identifier: str) -> None:
        self._integration = integration
        self._identifier = identifier

    async def invoke(self, tool_slug: str, params: dict[str, Any]) -> Observation:
        from lca.infrastructure.connectors.core.adapter import (
            format_connection_not_active_observation,
        )
        from lca.infrastructure.connectors.core.exceptions import ConnectionNotActiveError

        try:
            conn = self._integration.get_connection(self._identifier)
            if conn is None or not conn.is_active:
                raise ConnectionNotActiveError(
                    service=self._identifier,
                    user_id=self._integration.settings.default_user_id,
                    state=conn.status if conn else "NOT_CONNECTED",
                )
            content = await self._integration.execute_action(self._identifier, tool_slug, params)
        except ConnectionNotActiveError as exc:
            conn_entry = self._integration.get_connection(self._identifier)
            redirect = conn_entry.redirect_url if conn_entry else ""
            conn_id = conn_entry.connected_account_id if conn_entry else ""
            return format_connection_not_active_observation(
                exc,
                auth_url=redirect or "",
                connection_id=conn_id or "",
            )
        except Exception as exc:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload={"text": str(exc), "identifier": self._identifier, "tool_slug": tool_slug},
                error=str(exc),
            )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "text": content,
                "identifier": self._identifier,
                "tool_slug": tool_slug,
                "account_identity": getattr(conn, "account_identity", None) or conn.connected_account_id or "default",
                "state": {"content": [{"type": "text", "text": content}]},
            },
        )


def _validation_error(message: str) -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload={"text": message},
        error=message,
        extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
    )


_TOOL_GUIDANCE_OVERRIDES: dict[str, str] = {
    "GMAIL_FETCH_EMAILS": (
        "Fetches full email message details (including complete HTML bodies). "
        "NOTE: Defaults to only 1 message if max_results is omitted! If fetching multiple messages, "
        "always specify max_results (e.g. max_results=10). "
        "IMPORTANT: To check inbox overview, list recent emails, or search topics without fetching heavy bodies, "
        "strongly prefer GMAIL_LIST_THREADS instead."
    ),
    "GMAIL_LIST_THREADS": (
        "PREFERRED tool for checking inbox overview and listing recent emails. "
        "Retrieves discussions with message snippets, subjects, and participant summaries, "
        "making it much lighter and more reliable for listing recent emails."
    ),
}


def _augment_tool_description(tool_name: str, raw_description: str) -> str:
    override = _TOOL_GUIDANCE_OVERRIDES.get(tool_name)
    if override:
        return override
    return raw_description or f"Composio action {tool_name}"


def _action_manifest(identifier: str, label: str, tools: tuple[Any, ...]) -> ToolManifest:
    return ToolManifest(
        identifier=f"composio-{identifier}",
        type="builtin",
        api=tools,
        meta=ToolMeta(
            avatar="☁️",
            title=f"Composio: {label}",
            description=f"Composio actions for {label}",
        ),
    )


def build_tools(integration: ComposioIntegration | None) -> list[Tool]:
    if integration is None:
        return []

    tools: list[Tool] = build_tools_from_manifest(
        MANAGEMENT_MANIFEST,
        ComposioManagementExecutor(integration),
    )

    for conn in integration.list_active_connections():
        apis = tuple(
            ToolApi(
                name=tool.name,
                description=_augment_tool_description(tool.name, tool.description or ""),
                parameters=tool.input_schema or {"type": "object", "properties": {}},
                is_idempotent=False,
                namespace="ext",
            )
            for tool in conn.tools
        )
        if not apis:
            continue
        manifest = _action_manifest(conn.identifier, conn.label, apis)
        executor = ComposioActionExecutor(integration, conn.identifier)

        async def _invoke(
            _executor: ComposioActionExecutor, api_name: str, args: dict[str, Any]
        ) -> Observation:
            return await _executor.invoke(api_name, args)

        tools.extend(
            build_tools_from_manifest(
                manifest,
                executor,
                invoke_fn=lambda ex, api_name, args: _invoke(
                    cast("ComposioActionExecutor", ex), api_name, args
                ),
            )
        )

    return tools


def composio_services_context(integration: ComposioIntegration | None) -> str:
    if integration is None:
        return ""
    connected = [c.identifier for c in integration.list_active_connections()]
    if not connected:
        return "No Composio services connected."
    return "Connected Composio services: " + ", ".join(sorted(connected))
