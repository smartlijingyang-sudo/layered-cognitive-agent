"""act.execute — authorized Intent → EffectReceipt via SimpleSafeExecutor.

Sole world-touching node in the act phase (C10). Short-circuits
verdict ∈ {deny, skip} without calling tools. Shares ToolRegistry with
the former dispatch_tool path.
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind
from agent_lab.tools.registry import ToolRegistry
from lca.cognition.body.executor.safe_executor import SimpleSafeExecutor
from lca.contracts.models.team.role.team import (
    CacheConfig,
    RetryPolicy,
    ToolPermissionManifest,
)


@node(
    id="act.execute",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.EXECUTOR,
    description=(
        "Run one tool via LCA SimpleSafeExecutor when verdict=allow. "
        "deny/skip → synthetic receipt; never writes cognitive State."
    ),
    inputs=[PortInfo("authorized", kind=PortKind.INTENT, required=False)],
    outputs=[PortInfo("receipt", kind=PortKind.RECEIPT)],
    provides=["effect_receipt"],
    consumes=["tool_intent"],
    emits=["effect_receipt"],
    relates_to=["act.authorize", "act.observe"],
)
class ActExecute(Node):
    """Resolve a Tool by name and run it via SimpleSafeExecutor."""

    name = "act.execute"

    def execute(self, node, inputs):
        intent_port = node.config.get("from", "authorized")
        out_port = node.config.get("to", "receipt")
        intent_a = inputs.get(intent_port)
        content = _content(intent_a)
        verdict = content.get("verdict")
        tool_name = content.get("tool")
        decision_id = content.get("decision_id", "")
        action_type = content.get("action_type", "")

        if verdict == "skip" or content.get("effect_kind") == "no_effect":
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "no_effect",
                        "tool": tool_name or "__none__",
                        "decision_id": decision_id,
                        "action_type": action_type,
                        "response_text": content.get("response_text"),
                    },
                    schema_ref="tool.receipt.v1",
                )
            }

        if intent_a is None or verdict == "deny" or tool_name in (None, "__none__"):
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "denied",
                        "tool": tool_name,
                        "decision_id": decision_id,
                        "error": "grant denied" if verdict == "deny" else "missing tool",
                    },
                    schema_ref="tool.receipt.v1",
                )
            }

        args = content.get("args", {}) or {}
        if not isinstance(args, dict):
            args = {}

        registry = _registry()
        if not registry.contains(tool_name):
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "denied",
                        "tool": tool_name,
                        "decision_id": decision_id,
                        "error": f"tool not in registry: {tool_name!r}",
                    },
                    schema_ref="tool.receipt.v1",
                )
            }

        tool_range = tuple(node.config.get("tools", ()) or ())
        executor = SimpleSafeExecutor(
            ToolPermissionManifest(allowed_tools=sorted(tool_range or registry.names())),
        )
        tool = registry.get(tool_name)
        retry_policy = RetryPolicy(max_retries=int(node.config.get("max_retries", 0) or 0))
        cache_config = CacheConfig(enabled=bool(node.config.get("cache_enabled", False)))
        try:
            import asyncio

            obs = asyncio.run(
                executor.execute(
                    tool=tool,
                    args=args,
                    retry_policy=retry_policy,
                    cache_config=cache_config,
                )
            )
        except Exception as exc:
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "error",
                        "tool": tool_name,
                        "decision_id": decision_id,
                        "error": str(exc),
                    },
                    schema_ref="tool.receipt.v1",
                )
            }

        if obs.success:
            body = {
                "status": "ok",
                "tool": tool_name,
                "result": obs.payload,
                "decision_id": decision_id,
            }
        else:
            body = {
                "status": "error",
                "tool": tool_name,
                "error": obs.error or "unknown",
                "decision_id": decision_id,
            }
        return {
            out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content=body,
                schema_ref="tool.receipt.v1",
            )
        }


_REGISTRY_SINGLETON: dict[str, object] = {}


def configure_registry(registry: ToolRegistry) -> None:
    """Set the singleton registry. Called by the runner at boot."""
    _REGISTRY_SINGLETON["value"] = registry
    # Keep dispatch_tool's singleton in sync while that factory still exists.
    from agent_lab.nodes.tool.dispatch_tool.plugin import (
        configure_registry as _legacy_configure,
    )

    _legacy_configure(registry)


def _registry() -> ToolRegistry:
    from pathlib import Path

    registry = _REGISTRY_SINGLETON.get("value")
    if registry is not None:
        return registry  # type: ignore[return-value]
    registry = ToolRegistry()
    registry.load_from_yaml(Path(__file__).resolve().parents[3] / "tools" / "registry.yaml")
    _REGISTRY_SINGLETON["value"] = registry
    return registry


def _content(artifact: Any) -> dict[str, Any]:
    if artifact is None:
        return {}
    raw = getattr(artifact, "content", None)
    return raw if isinstance(raw, dict) else {}
