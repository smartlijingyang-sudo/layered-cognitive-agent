"""dispatch_tool — legacy factory; world effects go through act.execute Body.

Kept registered so old graph references resolve. New graphs use
``act.execute``. This node rebuilds a minimal Intent and calls the same
``SimpleBody.act`` path as act.execute (single world gate).
"""

from __future__ import annotations

from agent_lab.nodes.act.execute import body as act_body
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind
from agent_lab.tools.registry import ToolRegistry


@node(
    id="dispatch_tool",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.EXECUTOR,
    description=(
        "Legacy alias: run one tool via the same SimpleBody.act path as "
        "act.execute. Prefer act.execute in new graphs."
    ),
    inputs=[PortInfo("routed", kind=PortKind.INTENT, required=False)],
    outputs=[PortInfo("receipt", kind=PortKind.RECEIPT)],
    provides=["effect_receipt"],
    consumes=["tool_intent"],
    emits=["effect_receipt"],
    relates_to=["act.execute", "grant_check", "write_receipt"],
)
class DispatchTool(Node):
    """Thin legacy wrapper around act.execute's Body path."""

    name = "dispatch_tool"

    def execute(self, node, inputs):
        intent_port = node.config.get("from", "intent")
        out_port = node.config.get("to", "receipt")
        intent_a = inputs.get(intent_port)
        content = getattr(intent_a, "content", None) if intent_a else None
        if not isinstance(content, dict):
            content = {}

        if intent_a is None or content.get("verdict") == "deny":
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={"status": "denied"},
                    schema_ref="tool.receipt.v1",
                )
            }

        tool_name = content.get("tool")
        if tool_name in (None, "__none__"):
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={"status": "denied"},
                    schema_ref="tool.receipt.v1",
                )
            }

        lab = act_body.lab_tools()
        if not lab.contains(str(tool_name)):
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "denied",
                        "tool": tool_name,
                        "error": f"tool not in registry: {tool_name!r}",
                    },
                    schema_ref="tool.receipt.v1",
                )
            }

        tool_range = tuple(node.config.get("tools", ()) or ())
        stamped = {
            **content,
            "effect_kind": "use_tool",
            "action_type": "use_tool",
            "tool_calls": content.get("tool_calls")
            or [
                {
                    "call_id": content.get("call_id") or "",
                    "name": tool_name,
                    "arguments": content.get("args") or {},
                }
            ],
        }
        try:
            obs = act_body.run_body_act(
                stamped,
                allowed_tools=tool_range or lab.names(),
            )
        except Exception as exc:
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "error",
                        "tool": tool_name,
                        "error": str(exc),
                    },
                    schema_ref="tool.receipt.v1",
                )
            }

        return {
            out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content=act_body.observation_to_receipt(
                    obs,
                    decision_id=str(content.get("decision_id") or ""),
                    tool=str(tool_name),
                ),
                schema_ref="tool.receipt.v1",
            )
        }


_REGISTRY_SINGLETON: dict[str, object] = {}


def configure_registry(registry: ToolRegistry) -> None:
    """Legacy boot hook; forwards to act Body inventory."""
    _REGISTRY_SINGLETON["value"] = registry
    act_body.configure_lab_tools(registry)


def _registry() -> ToolRegistry:

    registry = _REGISTRY_SINGLETON.get("value")
    if registry is not None:
        return registry  # type: ignore[return-value]
    return act_body.lab_tools()
