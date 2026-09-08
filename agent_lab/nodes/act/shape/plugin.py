"""act.shape — Decision → ToolIntent | no_effect Intent.

Extracts an executable intent from an enforced Decision. Non-world
actions (respond / refuse / …) become a no_effect intent; call_tool
takes the first tool_call. Does not authorize or execute.
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="act.shape",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.PRODUCER,
    description=(
        "Decision → Intent. call_tool yields {tool, args}; other action_types "
        "yield effect_kind=no_effect. No grant check, no world side effect."
    ),
    inputs=[PortInfo("decision", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("intent", kind=PortKind.INTENT)],
    provides=["tool_intent"],
    consumes=["decision"],
    emits=["tool_intent"],
    relates_to=["act.authorize", "act.execute"],
)
class ActShape(Node):
    """Package Decision into a ToolIntent or no_effect Intent."""

    name = "act.shape"

    def execute(self, node, inputs):
        out_port = node.config.get("to", "intent")
        decision_a = inputs.get(node.config.get("from", "decision"))
        raw = _content(decision_a)

        # Legacy raw args ({tool, args}) still accepted for demos / tests.
        if "action_type" not in raw and isinstance(raw.get("tool"), str):
            return {
                out_port: Artifact(
                    kind=ArtifactKind.INTENT,
                    content={
                        "effect_kind": "call_tool",
                        "tool": raw["tool"],
                        "args": raw.get("args", {}) or {},
                        "decision_id": raw.get("decision_id", ""),
                    },
                    schema_ref="tool.intent.v1",
                )
            }

        action_type = str(raw.get("action_type") or "")
        decision_id = str(raw.get("decision_id") or "")

        if action_type == "call_tool":
            tool_calls = raw.get("tool_calls") or []
            first = tool_calls[0] if tool_calls else {}
            if not isinstance(first, dict):
                first = {}
            tool_name = str(first.get("name") or first.get("tool_name") or "")
            args = first.get("arguments") or first.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            if not tool_name:
                return {
                    out_port: Artifact(
                        kind=ArtifactKind.INTENT,
                        content={
                            "effect_kind": "no_effect",
                            "tool": "__none__",
                            "args": {},
                            "decision_id": decision_id,
                            "action_type": action_type,
                            "reason": "call_tool without tool_calls",
                        },
                        schema_ref="tool.intent.v1",
                    )
                }
            return {
                out_port: Artifact(
                    kind=ArtifactKind.INTENT,
                    content={
                        "effect_kind": "call_tool",
                        "tool": tool_name,
                        "args": args,
                        "call_id": str(first.get("call_id") or ""),
                        "decision_id": decision_id,
                        "action_type": action_type,
                    },
                    schema_ref="tool.intent.v1",
                )
            }

        return {
            out_port: Artifact(
                kind=ArtifactKind.INTENT,
                content={
                    "effect_kind": "no_effect",
                    "tool": "__none__",
                    "args": {},
                    "decision_id": decision_id,
                    "action_type": action_type or "respond",
                    "response_text": raw.get("response_text"),
                },
                schema_ref="tool.intent.v1",
            )
        }


def _content(artifact: Any) -> dict[str, Any]:
    if artifact is None:
        return {}
    raw = getattr(artifact, "content", None)
    return raw if isinstance(raw, dict) else {}
