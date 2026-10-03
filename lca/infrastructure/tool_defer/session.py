"""Per-run defer session: loaded-set, per-turn view, wire rendering.

Lifecycle: the run entry publishes one ``ToolDeferSession`` on the
ContextVar seam (mirroring ``current_tools_service`` in
``lca.infrastructure.runtime_plane.capability_bindings``).  Each turn,
``concept.tool.fork`` dispatch refreshes the per-turn view *after*
filtering/wrapping; ``think.history.assemble`` projects the model-visible
slice.  The loaded set is created once per run and reused across turns —
never rebuilt inside dispatch (dispatch runs every turn, see
``bundles/think_reason.yaml``).
"""

from __future__ import annotations

import difflib
import logging
from collections.abc import Sequence
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any

from lca.contracts.models.cognition.tool_defer import DeferMode, ToolNamespace
from lca.infrastructure.tool_defer.policy import DeferPolicy

if TYPE_CHECKING:
    from lca.contracts.protocols import Tool


log = logging.getLogger(__name__)

MCP_NAMESPACE_PREFIX = "mcp_"
"""Prefix for per-MCP-server virtual namespaces (e.g. ``mcp_corp``)."""


def _tool_to_spec(tool: Tool) -> dict[str, Any]:
    """Wire shape identical to ``think.history.assemble._tool_to_spec``.

    Kept local on purpose: infrastructure must not import L2 nodes.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


class ToolDeferSession:
    """Run-scoped defer state."""

    def __init__(self, policy: DeferPolicy) -> None:
        self._policy = policy
        self._loaded: set[str] = set()
        self._eager_tools: set[str] = set()
        self._namespaces: tuple[ToolNamespace, ...] = ()
        self._specs: dict[str, dict[str, Any]] = {}  # tool name -> wire spec

    @property
    def policy(self) -> DeferPolicy:
        return self._policy

    @property
    def loaded_namespaces(self) -> frozenset[str]:
        """Namespaces the agent has loaded so far this run."""
        return frozenset(self._loaded)

    @property
    def namespaces(self) -> tuple[ToolNamespace, ...]:
        """This turn's namespace view (turn order)."""
        return self._namespaces

    def update_turn(self, tools: Sequence[Tool]) -> None:
        """Refresh the per-turn view after fork filtering/wrapping.

        Fail-soft by design: a tool with a *missing* namespace must never
        kill the run here (2026-10-01: 6 runs died with 0 steps because a
        wrapper swallowed ``namespace``). Such tools are parked under the
        ``"unknown"`` pseudo-namespace in ``DEFERRED`` mode — fail-closed
        for *discovery* (the model must explicitly load it), never for the
        run itself. A warning is logged so the missing declaration stays
        observable.

        A *declared* namespace the policy has no description for is a policy
        misconfiguration and still fails fast here (ADR-0256 B2: 目录描述必填
        化); with ``DeferPolicy.default()`` this never triggers in production.
        Wiring-time fail-fast (``ToolsService.register`` raises; factories are
        covered by contract tests) catches undeclared tools even earlier.
        The loaded set is *not* reset.
        """
        grouped: dict[str, list[str]] = {}
        for tool in tools:
            ns = getattr(tool, "namespace", "") or ""
            if not ns:
                log.warning(
                    "tool_defer: tool %r has no namespace; "
                    "parking under 'unknown' (deferred)",
                    tool.name,
                )
                ns = "unknown"
            grouped.setdefault(ns, []).append(tool.name)
        self._namespaces = tuple(
            ToolNamespace(
                name=namespace,
                description=(
                    "未声明命名空间的工具（运行时兜底，deferred）"
                    if namespace == "unknown"
                    else self._describe(namespace, tool_names)
                ),
                mode=(
                    DeferMode.DEFERRED
                    if namespace == "unknown"
                    or namespace not in self._policy.eager_namespaces
                    else DeferMode.EAGER
                ),
                tool_names=tuple(tool_names),
            )
            for namespace, tool_names in grouped.items()
        )
        self._specs = {tool.name: _tool_to_spec(tool) for tool in tools}
        self._eager_tools = {tool.name for tool in tools if getattr(tool, "eager", False)}

    def _describe(self, namespace: str, tool_names: list[str]) -> str:
        override = self._policy.namespace_descriptions.get(namespace)
        if override:
            return override
        if namespace.startswith(MCP_NAMESPACE_PREFIX):
            server = namespace[len(MCP_NAMESPACE_PREFIX):]
            return (
                f"MCP 本地服务「{server}」的工具"
                f"（{len(tool_names)} 个），按需加载"
            )
        raise ValueError(
            f"namespace {namespace!r} has no description in policy; "
            f"known: {sorted(self._policy.namespace_descriptions.keys())}"
        )

    def _mcp_aliases(self) -> dict[str, str]:
        """Server-name alias -> canonical namespace, e.g. ``{'corp': 'mcp_corp'}``."""
        return {
            ns.name[len(MCP_NAMESPACE_PREFIX):]: ns.name
            for ns in self._namespaces
            if ns.name.startswith(MCP_NAMESPACE_PREFIX)
        }

    def resolve_namespace(self, name: str) -> str:
        """Canonical namespace for a model-supplied name.

        Exact match first (a declared namespace always wins over an MCP
        alias), then the MCP server-name alias (``'corp'`` -> ``'mcp_corp'``).
        Raises ``KeyError`` with close-match suggestions otherwise.
        """
        known = sorted(ns.name for ns in self._namespaces)
        if name in known:
            return name
        aliases = self._mcp_aliases()
        if name in aliases:
            return aliases[name]
        candidates = known + sorted(aliases)
        suggestions = difflib.get_close_matches(name, candidates, n=3, cutoff=0.6)
        detail = ""
        if suggestions:
            rendered = []
            for s in suggestions:
                if s in aliases:
                    rendered.append(f"'{aliases[s]}'（别名 '{s}'）")
                else:
                    rendered.append(f"'{s}'")
            detail = "；您是想找 " + "、".join(rendered) + " 吗？"
        raise KeyError(
            f"unknown tool namespace {name!r}{detail}"
            f"；已知命名空间：{', '.join(known) or '(none)'}"
        )

    def search_catalog(self, query: str) -> list[dict[str, Any]]:
        """Keyword discovery over the local namespace catalog (no schema load).

        Token-based, case-insensitive (Chinese supported): the query is split
        on whitespace and a namespace matches when at least one token hits
        the namespace name, its description, a tool name or a tool
        description. Rank: token coverage desc, then namespace-name hit >
        tool-name hit > description hit.
        Only local namespaces are covered (declared + MCP virtual) — the
        skill marketplace is searched separately via ``search_skill``.
        """
        tokens = [t for t in query.strip().lower().split() if t]
        if not tokens:
            return []
        hits: list[dict[str, Any]] = []
        for ns in self._namespaces:
            ns_name = ns.name.lower()
            ns_desc = ns.description.lower()
            tool_descs = {
                tname: (
                    self._specs.get(tname, {}).get("function", {}).get("description", "")
                    or ""
                ).lower()
                for tname in ns.tool_names
            }
            matched_tokens = 0
            name_hit = False
            matched_tools: list[str] = []
            for tok in tokens:
                tok_name_hit = tok in ns_name
                tok_desc_hit = tok in ns_desc
                tok_tools = [
                    tname
                    for tname in ns.tool_names
                    if tok in tname.lower() or tok in tool_descs[tname]
                ]
                if tok_name_hit or tok_desc_hit or tok_tools:
                    matched_tokens += 1
                name_hit = name_hit or tok_name_hit
                for tname in tok_tools:
                    if tname not in matched_tools:
                        matched_tools.append(tname)
            if matched_tokens == 0:
                continue
            kind_rank = 0 if name_hit else (1 if matched_tools else 2)
            source = "mcp" if ns.name.startswith(MCP_NAMESPACE_PREFIX) else "declared"
            hits.append(
                {
                    "namespace": ns.name,
                    "description": ns.description,
                    "matched_tools": matched_tools,
                    "source": source,
                    "_rank": (kind_rank, -matched_tokens, ns.name),
                }
            )
        hits.sort(key=lambda h: h["_rank"])
        for h in hits:
            del h["_rank"]
        return hits

    def load_namespace(self, namespace: str) -> dict[str, Any]:
        """Mark *namespace* loaded and return its full wire specs.

        Idempotent — a second load returns the same payload.  Raises
        ``KeyError`` with the known namespaces on unknown input.
        """
        canonical = self.resolve_namespace(namespace)
        target = next(ns for ns in self._namespaces if ns.name == canonical)
        self._loaded.add(canonical)
        return {
            "namespace": canonical,
            "description": target.description,
            "tools": [self._specs[name] for name in target.tool_names],
        }

    def load_namespaces(self, namespaces: Sequence[str]) -> dict[str, Any]:
        """Load several namespaces at once; return the merged payload.

        Semantics = one :meth:`load_namespace` call per name (already
        idempotent), with the wire specs concatenated in the given order.
        A repeated name contributes its tools once; an unknown name raises
        :meth:`load_namespace` ``KeyError`` unchanged.
        """
        loaded: list[str] = []
        tools: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for namespace in namespaces:
            payload = self.load_namespace(namespace)
            canonical = payload["namespace"]
            if canonical not in loaded:
                loaded.append(canonical)
            for tool_spec in payload["tools"]:
                tname = tool_spec["function"]["name"]
                if tname not in seen_names:
                    seen_names.add(tname)
                    tools.append(tool_spec)
        return {"namespaces": loaded, "tools": tools}

    def render_turn(self) -> tuple[tuple[dict[str, Any], ...], str]:
        """Project ``(wire_specs, catalog_text)`` for this turn.

        Eager and already-loaded namespaces contribute full specs;
        unloaded deferred namespaces contribute one catalog line each.
        A disabled policy (or a session with no turn view yet) renders
        the legacy full projection with no catalog.
        """
        if not self._policy.enabled:
            return tuple(self._specs.values()), ""
        if not self._namespaces:
            return (), ""
        # Defer is only coherent when the loader itself is on the wire.
        # A catalog that points at a missing tool_search, with an empty
        # tools array, is a deadlock. Fall back to the full projection.
        eager_present = any(
            namespace.name in self._policy.eager_namespaces for namespace in self._namespaces
        )
        if not eager_present:
            return tuple(self._specs.values()), ""
        wire: list[dict[str, Any]] = []
        catalog_lines: list[str] = []
        for namespace in self._namespaces:
            if namespace.mode == DeferMode.EAGER or namespace.name in self._loaded:
                wire.extend(self._specs[name] for name in namespace.tool_names)
            else:
                has_deferred = False
                for name in namespace.tool_names:
                    if name in self._eager_tools:
                        wire.append(self._specs[name])
                    else:
                        has_deferred = True
                if has_deferred:
                    catalog_lines.append(f"- {namespace.name}: {namespace.description}")
        catalog = ""
        if catalog_lines:
            catalog = (
                "Deferred tool namespaces (not yet loaded):\n"
                + "\n".join(catalog_lines)
                + f"\n{self._policy.discovery_rule}"
            )
        return tuple(wire), catalog


_defer_session: ContextVar[ToolDeferSession | None] = ContextVar(
    "lca_tool_defer_session", default=None
)


def set_current_defer_session(
    session: ToolDeferSession,
) -> Token[ToolDeferSession | None]:
    """Publish *session* for this run; call at the run entry.

    Returns the token; the run entry must reset it in ``finally``.
    """
    return _defer_session.set(session)


def reset_current_defer_session(token: Token[ToolDeferSession | None]) -> None:
    """Release the run's defer session."""
    _defer_session.reset(token)


def current_defer_session() -> ToolDeferSession | None:
    """The ambient defer session, or ``None`` on legacy paths (tests)."""
    return _defer_session.get()


__all__ = [
    "ToolDeferSession",
    "current_defer_session",
    "reset_current_defer_session",
    "set_current_defer_session",
]
