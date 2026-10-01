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

from collections.abc import Mapping, Sequence
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any

from lca.contracts.models.cognition.tool_defer import DeferMode, ToolNamespace
from lca.infrastructure.tool_defer.policy import DeferPolicy

if TYPE_CHECKING:
    from lca.contracts.protocols import Tool


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

    def update_turn(self, tools: Sequence[Tool], namespaces: Mapping[str, str]) -> None:
        """Refresh the per-turn view after fork filtering/wrapping.

        ``namespaces`` maps ``tool.name`` → factory key (from
        ``ToolsService.tool_namespaces``).  Tools missing from the map get
        their own single-tool namespace.  The loaded set is *not* reset.
        """
        grouped: dict[str, list[str]] = {}
        for tool in tools:
            grouped.setdefault(namespaces.get(tool.name, tool.name), []).append(tool.name)
        self._namespaces = tuple(
            ToolNamespace(
                name=namespace,
                description=self._describe(namespace, tool_names),
                mode=(
                    DeferMode.EAGER
                    if namespace in self._policy.eager_namespaces
                    else DeferMode.DEFERRED
                ),
                tool_names=tuple(tool_names),
            )
            for namespace, tool_names in grouped.items()
        )
        self._specs = {tool.name: _tool_to_spec(tool) for tool in tools}

    def _describe(self, namespace: str, tool_names: list[str]) -> str:
        override = self._policy.namespace_descriptions.get(namespace)
        if override:
            return override
        shown = ", ".join(tool_names[:8])
        suffix = f" (+{len(tool_names) - 8} more)" if len(tool_names) > 8 else ""
        return f"{len(tool_names)} tools: {shown}{suffix}"

    def load_namespace(self, namespace: str) -> dict[str, Any]:
        """Mark *namespace* loaded and return its full wire specs.

        Idempotent — a second load returns the same payload.  Raises
        ``KeyError`` with the known namespaces on unknown input.
        """
        target = next((ns for ns in self._namespaces if ns.name == namespace), None)
        if target is None:
            known = ", ".join(sorted(ns.name for ns in self._namespaces)) or "(none)"
            raise KeyError(f"unknown tool namespace {namespace!r}; known: {known}")
        self._loaded.add(namespace)
        return {
            "namespace": namespace,
            "description": target.description,
            "tools": [self._specs[name] for name in target.tool_names],
        }

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
                # 一行一个 namespace，不再重复拼接 loading hint；提示只保留
                # 在末尾的 discovery_rule，减少目录文本的重复膨胀。
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
