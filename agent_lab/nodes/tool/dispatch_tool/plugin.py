"""dispatch_tool node — run a tool via LCA SimpleSafeExecutor directly.

Fusion refactor (2026-09-08): removed LcaBodyProvider adapter layer.
This node now imports the LCA SimpleSafeExecutor and ToolPermissionManifest
directly. cordis-gated; requires `uv run` (or a venv with cordis installed).

Configuration (node.config):
  - tools       : list[str] — tool range (which names this dispatch may invoke)
  - from / to   : port renames (default: routed -> receipt)

Behaviour:
  - Tools are resolved from the agent_lab ToolRegistry (the single
    named-tool inventory at agent_lab/tools/registry.yaml).
  - If the routed intent's tool name is outside the declared range,
    SimpleSafeExecutor denies and the chain (write_receipt / integrate)
    handles the denial normally.
  - No fallback stub; if cordis is missing, import fails immediately
    (fail-loud per ADR-0186).
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind
from agent_lab.tools.registry import ToolRegistry

# Direct LCA imports (cordis-gated, fail-loud if missing).
from lca.cognition.body.executor.safe_executor import SimpleSafeExecutor
from lca.contracts.models.team.role.team import ToolPermissionManifest


@node(
    id="dispatch_tool",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.EXECUTOR,
    description=(
        "Run one tool via LCA SimpleSafeExecutor bound to a named range. "
        "Tools come from agent_lab ToolRegistry (named-tool inventory)."
    ),
    inputs=[PortInfo("routed", kind=PortKind.INTENT, required=False)],
    outputs=[PortInfo("receipt", kind=PortKind.RECEIPT)],
    provides=["effect_receipt"],
    consumes=["tool_intent"],
    emits=["effect_receipt"],
    relates_to=["grant_check", "write_receipt", "integrate_observation"],
)
class DispatchTool(Node):
    """Resolve a Tool by name and run it via SimpleSafeExecutor."""

    name = "dispatch_tool"

    def execute(self, node, inputs):
        intent_port = node.config.get("from", "intent")
        out_port = node.config.get("to", "receipt")
        intent_a = inputs.get(intent_port)

        # denial short-circuit
        if intent_a is None or intent_a.content.get("verdict") == "deny":
            return {out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content={"status": "denied"},
                schema_ref="tool.receipt.v1",
            )}

        tool_name = intent_a.content.get("tool")
        if tool_name in (None, "__none__"):
            return {out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content={"status": "denied"},
                schema_ref="tool.receipt.v1",
            )}

        args = intent_a.content.get("args", {})
        registry = _registry()
        if not registry.contains(tool_name):
            return {out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content={
                    "status": "denied",
                    "tool": tool_name,
                    "error": f"tool not in this dispatch's range: {tool_name!r}",
                },
                schema_ref="tool.receipt.v1",
            )}

        tool_range = tuple(node.config.get("tools", ()) or ())
        executor = SimpleSafeExecutor(
            ToolPermissionManifest(allowed_tools=sorted(tool_range or registry.names())),
        )
        tool = registry.get(tool_name)
        try:
            import asyncio
            obs = asyncio.run(executor.execute(tool=tool, args=args))
        except Exception as exc:
            return {out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content={"status": "error", "tool": tool_name, "error": str(exc)},
                schema_ref="tool.receipt.v1",
            )}

        if obs.success:
            content = {"status": "ok", "tool": tool_name, "result": obs.payload}
        else:
            content = {
                "status": "error",
                "tool": tool_name,
                "error": obs.error or "unknown",
            }
        return {out_port: Artifact(
            kind=ArtifactKind.RECEIPT, content=content,
            schema_ref="tool.receipt.v1",
        )}


# ---------------------------------------------------------------------------
# Singleton ToolRegistry — agent_lab's non-executable named-tool inventory.
# ---------------------------------------------------------------------------

_REGISTRY_SINGLETON: dict[str, object] = {}


def configure_registry(registry: ToolRegistry) -> None:
    """Set the singleton registry. Called by the runner at boot."""
    _REGISTRY_SINGLETON["value"] = registry


def _registry() -> ToolRegistry:
    from pathlib import Path
    registry = _REGISTRY_SINGLETON.get("value")
    if registry is None:
        registry = ToolRegistry()
        registry.load_from_yaml(Path(__file__).resolve().parents[3] / "tools" / "registry.yaml")
        _REGISTRY_SINGLETON["value"] = registry
    return registry  # type: ignore[return-value]
