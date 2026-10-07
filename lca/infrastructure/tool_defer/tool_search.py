"""The ``tool_search`` tool — the agent's loader for deferred namespaces.

Registered as an ordinary ``Tool`` through the Tier-2 tools provider
(``lca.plugins.act.tools``), in its own ``"tool_search"`` namespace, and
kept eager by ``DeferPolicy`` so the loader is always injectable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.tool_defer.session import current_defer_session


def _error(message: str) -> Observation:
    # docs/specs/tool-failure-recovery.md §3: 参数校验失败 → failure_kind="validation"。
    # 带分类的失败回到 think 重规划（act.main → think.main），而不是被
    # act.observe.terminate_decide 读成 host 派发失败而终止 run。
    return Observation(
        observation_id="tool_search:error",
        success=False,
        payload={"error": message},
        error=message,
        extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
    )


@dataclass(frozen=True, slots=True)
class _ArgShape:
    """namespace / namespaces / query 存在性分类（validate 的严格口径）。

    execute() 与 validate() 共用的单点真值：空字符串 / 空 list /
    空白 query 一律视为"未提供"。
    """

    has_namespace: bool
    has_namespaces: bool
    has_query: bool


def _classify_args(args: dict[str, Any]) -> _ArgShape:
    """统一的参数形状分类器：两处调用点共用同一口径。"""
    return _ArgShape(
        has_namespace=("namespace" in args and isinstance(args["namespace"], str) and bool(args["namespace"])),
        has_namespaces=(
            "namespaces" in args
            and isinstance(args["namespaces"], list)
            and bool(args["namespaces"])
        ),
        has_query=("query" in args and isinstance(args["query"], str) and bool(args["query"].strip())),
    )


class ToolSearchTool(Tool):
    """Discover and load deferred tool namespaces on demand.

    Two modes (local-first, nothing is stuffed into the prompt):

    - ``query`` — intent discovery WITHOUT loading schemas: keyword search
      over the local namespace catalog (declared namespaces + per-MCP-server
      virtual namespaces like ``mcp_corp``). Use this when you are not sure
      which namespace holds a capability.
    - ``namespace`` / ``namespaces`` — load full parameter schemas of the
      named namespace(s). Each MCP server is addressable as
      ``mcp_<server>`` (e.g. ``mcp_corp``); the bare server name also works
      as an alias (``corp`` -> ``mcp_corp``).

    Loading is idempotent — loading an already-loaded namespace returns
    its schemas again without side effects. For the skill marketplace
    (non-local skills), use ``search_skill`` instead.
    """

    name: ClassVar[str] = "tool_search"
    namespace: ClassVar[str] = "core"
    description: ClassVar[str] = (
        "Discover or load deferred tool namespaces on demand. "
        "query=<keywords>: find which local namespace holds a capability "
        "(no schemas loaded; MCP servers appear as mcp_<server>). "
        "namespace=<name>: load full schemas (alias: bare MCP server name, "
        "e.g. 'corp' -> 'mcp_corp'). Loading is idempotent."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": ('Namespace key from the deferred catalog, e.g. "file".'),
            },
            "namespaces": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    'List of namespace keys to load in batch, e.g. ["file", "memory"].'
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Intent keywords to discover namespaces WITHOUT loading schemas, "
                    "e.g. 'OA 审批'. Searches namespace names, descriptions, tool "
                    "names and tool descriptions (local only: declared namespaces "
                    "+ MCP servers as mcp_<server>). Use search_skill for the "
                    "marketplace."
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
        shape = _classify_args(args)
        if shape.has_namespaces:
            try:
                payload = session.load_namespaces(args["namespaces"])
            except KeyError as exc:
                return _error(f"tool_search: {exc}")
            return Observation(
                observation_id=f"tool_search:{','.join(payload['namespaces'])}",
                success=True,
                payload=payload,
            )
        if shape.has_namespace:
            try:
                payload = session.load_namespace(args["namespace"])
            except KeyError as exc:
                return _error(f"tool_search: {exc}")
            return Observation(
                observation_id=f"tool_search:{payload['namespace']}",
                success=True,
                payload=payload,
            )
        if shape.has_query:
            hits = session.search_catalog(args["query"])
            return Observation(
                observation_id="tool_search:query",
                success=True,
                payload={"query": args["query"], "namespaces": hits},
            )
        return _error(
            "tool_search: one of 'namespace', 'namespaces' or 'query' must be provided"
        )

    def validate(self, args: dict[str, Any]) -> str | None:
        shape = _classify_args(args)
        if not shape.has_namespace and not shape.has_namespaces and not shape.has_query:
            return (
                "One of 'namespace' (str), 'namespaces' (list[str]) "
                "or 'query' (str) must be provided"
            )
        if shape.has_namespace and not isinstance(args["namespace"], str):
            return "'namespace' must be a non-empty string"
        if shape.has_namespaces and not all(
            isinstance(x, str) and bool(x) for x in args["namespaces"]
        ):
            return "'namespaces' must be a list of non-empty strings"
        return None


def tool_search_factory(bindings: object) -> ToolSearchTool:
    """``ToolsService`` factory — registered as the ``tool_search`` namespace."""
    del bindings
    return ToolSearchTool()


__all__ = ["ToolSearchTool", "tool_search_factory"]
