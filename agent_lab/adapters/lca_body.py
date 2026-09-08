"""Adapter: agent_lab tool dispatch ↔ LCA SimpleSafeExecutor.

LCA contracts consumed (read-only):
  - lca.contracts.protocols.runtime.infra.infra.Tool  (async execute Protocol)
  - lca.cognition.body.executor.safe_executor.SimpleSafeExecutor
  - lca.contracts.models.team.role.team.{RetryPolicy, CacheConfig, ToolPermissionManifest}
  - lca.contracts.models.core.execution.decision.Observation

agent_lab provides (this file):
  - LcaBodyProvider: receives a tool range (list of tool names) from the
    caller, resolves each name to a real LCA Tool via the supplied
    ``ToolRegistry``, builds a ``SimpleSafeExecutor`` whose allowlist is
    that range, and runs the tool.  Returns an agent_lab receipt artifact.

Tools are NEVER fabricated here.  They are looked up by name from a
:class:`agent_lab.tools.registry.ToolRegistry` — the registry is the
single named-tool inventory of the agent loop and is loaded from
``agent_lab/tools/registry.yaml`` at boot.

The async-to-sync bridge uses ``asyncio.run()`` inside the sync
``node.execute()`` body, just like before.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

if TYPE_CHECKING:
    from agent_lab.tools.registry import ToolRegistry


class LcaBodyProvider:
    """Wraps SimpleSafeExecutor + a per-dispatch tool range.

    A dispatch graph declares a *range* of tool names in its
    ``dispatch`` node's ``config.tools:`` list.  We resolve each name to
    a real LCA ``Tool`` instance via the supplied ``ToolRegistry`` and
    pass that allowlist to ``SimpleSafeExecutor``.

    The provider itself is the only thing the dispatch node needs to
    know about: ``LcaBodyProvider(tool_registry=..., tool_range=...)``.
    The range is intentionally re-asserted on every call so a graph that
    wants to shrink its surface mid-loop is free to do so.

    Boundary:
      - the registry owns tool *identity* (name, schema)
      - the provider owns tool *execution* (SimpleSafeExecutor plumbing)
      - the dispatch graph owns tool *selection* (which names this
        turn is allowed to invoke)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        tool_range: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        # Lazy imports so agent_lab boots without lca.
        from lca.cognition.body.executor.safe_executor import SimpleSafeExecutor
        from lca.contracts.models.team.role.team import (
            CacheConfig,
            RetryPolicy,
            ToolPermissionManifest,
        )

        self._registry = tool_registry
        # Resolve the range into a concrete {name: Tool} mapping.  If no
        # range is given, fall back to "everything in the registry" —
        # callers are expected to be explicit in production graphs.
        if tool_range is None:
            range_names = tool_registry.names()
        else:
            range_names = tuple(tool_range)
            missing = [n for n in range_names if not tool_registry.contains(n)]
            if missing:
                raise KeyError(f"tool_range references tools not in registry: {missing!r}")
        self._tools: dict[str, Any] = {n: tool_registry.get(n) for n in range_names}
        allow = set(self._tools.keys())
        self._executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=sorted(allow)))
        self._retry = RetryPolicy() if RetryPolicy else None
        self._cache = CacheConfig() if CacheConfig else None

    # ---- introspection (debug / self-describe) ----------------------------

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools.keys()))

    # ---- execution --------------------------------------------------------

    def invoke(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Run a tool through SimpleSafeExecutor.  Sync bridge via asyncio.run.

        Returns a dict suitable for an agent_lab receipt artifact:
          ``{"status": "ok" | "error" | "denied", "tool": str, ...}``
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return {
                "status": "denied",
                "tool": tool_name,
                "error": f"tool not in this dispatch's range: {tool_name!r}",
            }
        try:
            obs = asyncio.run(
                self._executor.execute(
                    tool=tool,  # type: ignore[arg-type]
                    args=args,
                    retry_policy=self._retry,  # type: ignore[arg-type]
                    cache_config=self._cache,  # type: ignore[arg-type]
                    invocation_id="",
                )
            )
        except Exception as exc:
            return {"status": "error", "tool": tool_name, "error": str(exc)}
        if obs.success:
            return {"status": "ok", "tool": tool_name, "result": obs.payload}
        return {
            "status": "error",
            "tool": tool_name,
            "error": obs.error or "unknown",
        }

    def to_receipt_artifact(
        self,
        tool_name: str,
        args: dict[str, Any],
        port: str = "receipt",
    ) -> Artifact:
        return Artifact(
            kind=ArtifactKind.RECEIPT,
            content=self.invoke(tool_name, args),
            schema_ref="tool.receipt.v1",
        )


__all__ = ["LcaBodyProvider"]
