"""The ``tool_search`` tool — the agent's loader for deferred namespaces.

Registered as an ordinary ``Tool`` through the Tier-2 tools provider
(``lca.plugins.act.tools``), in its own ``"tool_search"`` namespace, and
kept eager by ``DeferPolicy`` so the loader is always injectable.
"""

from __future__ import annotations

from typing import Any, ClassVar

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.tool_defer.session import current_defer_session


def _error(message: str) -> Observation:
    return Observation(
        observation_id="tool_search:error",
        success=False,
        payload={"error": message},
        error=message,
    )


class ToolSearchTool(Tool):
    """Load the full parameter schemas of one deferred tool namespace.

    The model's catalog lists deferred namespaces as one-liners; calling
    this tool marks the namespace loaded — its full schemas inject from
    the next turn on, and the load result is also returned immediately so
    the agent can inspect signatures before calling.
    """

    name: ClassVar[str] = "tool_search"
    namespace: ClassVar[str] = "core"
    description: ClassVar[str] = (
        "Load the full tool schemas for a deferred namespace. Namespaces "
        "not listed in the per-turn tool schemas appear only as one-line "
        "catalog entries; call this to make their tools available. "
        "Loading is idempotent — loading an already-loaded namespace "
        "returns its schemas again without side effects."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": (
                    "Namespace key from the deferred catalog, "
                    'e.g. "file".'
                ),
            },
            "namespaces": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of namespace keys to load in batch, "
                    'e.g. ["file", "memory"].'
                ),
            },
        },
        "additionalProperties": False,
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return _error(f"tool_search: {err}")
        session = current_defer_session()
        if session is None:
            return _error("tool_search: no defer session bound to this run")
        if "namespaces" in args and isinstance(args["namespaces"], list):
            try:
                payload = session.load_namespaces(args["namespaces"])
            except KeyError as exc:
                return _error(f"tool_search: {exc}")
            return Observation(
                observation_id=f"tool_search:{','.join(payload['namespaces'])}",
                success=True,
                payload=payload,
            )
        namespace = args["namespace"]
        try:
            payload = session.load_namespace(namespace)
        except KeyError as exc:
            return _error(f"tool_search: {exc}")
        return Observation(
            observation_id=f"tool_search:{payload['namespace']}",
            success=True,
            payload=payload,
        )

    def validate(self, args: dict[str, Any]) -> str | None:
        has_ns = "namespace" in args and isinstance(args["namespace"], str) and bool(args["namespace"])
        has_nss = "namespaces" in args and isinstance(args["namespaces"], list) and bool(args["namespaces"])
        if not has_ns and not has_nss:
            return "Either 'namespace' (str) or 'namespaces' (list[str]) must be provided"
        if has_ns and not isinstance(args["namespace"], str):
            return "'namespace' must be a non-empty string"
        if has_nss and not all(isinstance(x, str) and bool(x) for x in args["namespaces"]):
            return "'namespaces' must be a list of non-empty strings"
        return None


def tool_search_factory(bindings: object) -> ToolSearchTool:
    """``ToolsService`` factory — registered as the ``tool_search`` namespace."""
    del bindings
    return ToolSearchTool()


__all__ = ["ToolSearchTool", "tool_search_factory"]
