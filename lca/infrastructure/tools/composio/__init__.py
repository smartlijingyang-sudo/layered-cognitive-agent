"""Composio LLM tools — connect + dynamic actions from active connections."""

from __future__ import annotations

from typing import Any, cast

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
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
                "(e.g. google-drive, gmail, slack). Returns an authorization URL "
                "when user action is required."
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
        text = (
            f"To connect {conn.label}, open this authorization link and complete sign-in:\n\n"
            f"{redirect}\n\n"
            "After authorization the OAuth callback on LCA will refresh the connection automatically."
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "text": text,
                "identifier": service,
                "connected": False,
                "redirect_url": redirect,
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
        try:
            content = await self._integration.execute_action(self._identifier, tool_slug, params)
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
