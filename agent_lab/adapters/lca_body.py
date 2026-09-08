"""Adapter: agent_lab tool dispatch ↔ LCA SimpleSafeExecutor.

LCA contracts consumed (read-only):
  - lca.contracts.protocols.runtime.infra.infra.Tool  (async execute Protocol)
  - lca.cognition.body.executor.safe_executor.SimpleSafeExecutor
  - lca.contracts.models.team.role.team.{RetryPolicy, CacheConfig, ToolPermissionManifest}
  - lca.contracts.models.core.execution.decision.Observation

agent_lab provides (this file):
  - ToolShim: satisfies LCA's Tool Protocol by wrapping a sync callable
  - LcaBodyProvider: invokes SimpleSafeExecutor.execute(tool, args, ...) for real,
    returns an agent_lab receipt artifact.

The async-to-sync bridge uses asyncio.run() inside the sync node.execute() body.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def _build_tool_from_factory(entry: dict) -> ToolShim:
    """Build a ToolShim from a ``{ref: module:Class, kwargs: {...}}`` dict.

    The kwargs dict may itself contain a ``callable_ref`` key — a
    ``module:function`` path — which the resolver turns into the actual
    Python callable before passing it to the ToolShim constructor.
    """
    ref = entry["ref"]
    kwargs = dict(entry.get("kwargs", {}) or {})
    module_name, _, class_name = ref.partition(":")
    if not module_name or not class_name:
        raise ValueError(f"tool factory ref must be 'module:Class', got {ref!r}")
    # Resolve callable_ref: module:function -> actual function
    if "callable_ref" in kwargs:
        cmod, _, cfn = kwargs["callable_ref"].partition(":")
        cmod_obj = importlib.import_module(cmod)
        kwargs["_callable"] = getattr(cmod_obj, cfn)
        kwargs.pop("callable_ref", None)
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    return cls(**kwargs)

# ---------- Tool Protocol shim --------------------------------------------

@dataclass
class ToolShim:
    """Satisfies LCA's Tool Protocol by wrapping a sync or async callable.

    The Protocol declares name/description/parameters/is_idempotent/
    effect_kind/default_timeout_s as ClassVar; we set them as instance
    attributes because the Protocol uses @runtime_checkable so duck-typing
    on instance attributes works too.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    is_idempotent: bool
    effect_kind: str              # "ephemeral" | "persistent" | "stateful_once"
    default_timeout_s: int
    _callable: Callable[[dict[str, Any]], Any]

    async def execute(self, args: dict[str, Any]):
        # Lazy import to keep agent_lab bootable without lca.
        from lca.contracts.atoms.ids.ids import new_id
        from lca.contracts.models.core.execution.decision import Observation

        result = self._callable(args)
        if inspect.iscoroutine(result):
            result = await result
        if isinstance(result, Observation):
            return result
        # Wrap raw value into a minimal Observation (text payload).
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=result,
        )

    def validate(self, args: dict[str, Any]) -> str | None:
        return None


# ---------- LcaBodyProvider ------------------------------------------------

class LcaBodyProvider:
    """Wraps SimpleSafeExecutor + a dict of Tool shims.

    invoke(tool, args) -> dict (LCA Observation turned into agent_lab receipt).

    Accepts either:
      - ``tools=``: pre-built dict of ToolShim (Python-side setup)
      - ``tool_factories=``: list of ``{"ref": "module:Class", "kwargs": {...}}``
        factory refs the provider uses to build ToolShims on init
      - ``allowed_tools=``: tuple of tool names; falls back to factory names
    """

    def __init__(
        self,
        tools: dict[str, ToolShim] | None = None,
        allowed_tools: tuple[str, ...] | None = None,
        *,
        tool_factories: list[dict] | None = None,
    ) -> None:
        # Lazy import so agent_lab boots without lca.
        from lca.cognition.body.executor.safe_executor import SimpleSafeExecutor
        from lca.contracts.models.team.role.team import (
            CacheConfig,
            RetryPolicy,
            ToolPermissionManifest,
        )

        self._tools: dict[str, ToolShim] = dict(tools or {})
        # Build tools from factory refs (config-driven path).
        for entry in tool_factories or []:
            shim = _build_tool_from_factory(entry)
            self._tools[shim.name] = shim
        allow = set(allowed_tools or self._tools.keys())
        self._executor = SimpleSafeExecutor(
            ToolPermissionManifest(allowed_tools=list(allow))
        )
        self._retry = RetryPolicy() if RetryPolicy else None
        self._cache = CacheConfig() if CacheConfig else None

    def register_tool(self, tool: ToolShim) -> None:
        self._tools[tool.name] = tool

    def invoke(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Synchronously call SimpleSafeExecutor.execute(...) for the named tool."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return {"status": "denied", "tool": tool_name, "error": "tool not registered"}
        # asyncio.run to bridge sync -> async. Safe inside a sync context.
        try:
            obs = asyncio.run(
                self._executor.execute(
                    tool=tool,                # type: ignore[arg-type]
                    args=args,
                    retry_policy=self._retry,    # type: ignore[arg-type]
                    cache_config=self._cache,    # type: ignore[arg-type]
                    invocation_id="",
                )
            )
        except Exception as exc:
            return {"status": "error", "tool": tool_name, "error": str(exc)}
        # Map Observation -> dict (status / tool / result)
        if obs.success:
            return {"status": "ok", "tool": tool_name, "result": obs.payload}
        return {"status": "error", "tool": tool_name, "error": obs.error or "unknown"}

    def to_receipt_artifact(self, tool_name: str, args: dict[str, Any], port: str = "receipt") -> Artifact:
        return Artifact(
            kind=ArtifactKind.RECEIPT,
            content=self.invoke(tool_name, args),
            schema_ref="tool.receipt.v1",
        )


def _echo_factory_callable(args: dict[str, Any]) -> str:
    """Demo callable referenced by the YAML tool_factories block."""
    return f"echo({args})"


def _calc_factory_callable(args: dict[str, Any]) -> str:
    """Demo callable referenced by the YAML tool_factories block."""
    expr = str(args.get("expr", "0"))
    return str(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307 — demo only
