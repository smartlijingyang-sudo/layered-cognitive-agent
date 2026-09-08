"""act.execute — authorized Intent → EffectReceipt via SimpleBody.act.

Sole Body entry in the act phase (C10). deny/skip short-circuit without
Body; allow runs ``SimpleBody.act`` for use_tool / respond / stop / ask_human.
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.act.execute import body as act_body
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind
from agent_lab.tools.registry import ToolRegistry
from lca.contracts.models.core.execution.result import ApprovalPendingError

_TOOL_KINDS = frozenset({"use_tool", "call_tool"})


@node(
    id="act.execute",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.EXECUTOR,
    description=(
        "Allow → SimpleBody.act (use_tool/respond/stop/ask_human); "
        "deny/skip → synthetic receipt. Never writes cognitive State."
    ),
    inputs=[PortInfo("authorized", kind=PortKind.INTENT, required=False)],
    outputs=[PortInfo("receipt", kind=PortKind.RECEIPT)],
    provides=["effect_receipt"],
    consumes=["tool_intent"],
    emits=["effect_receipt"],
    relates_to=["act.authorize", "act.observe"],
)
class ActExecute(Node):
    """Dispatch authorized intents through LCA SimpleBody."""

    name = "act.execute"

    def execute(self, node, inputs):
        intent_port = node.config.get("from", "authorized")
        out_port = node.config.get("to", "receipt")
        intent_a = inputs.get(intent_port)
        content = _content(intent_a)
        verdict = content.get("verdict")
        tool_name = content.get("tool")
        decision_id = content.get("decision_id", "")
        action_type = str(content.get("action_type") or "")
        effect_kind = str(content.get("effect_kind") or "")

        if intent_a is None or verdict == "skip" or effect_kind == "no_effect":
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "no_effect",
                        "tool": tool_name or "__none__",
                        "decision_id": decision_id,
                        "action_type": action_type,
                        "response_text": content.get("response_text"),
                        "reason": content.get("reason"),
                    },
                    schema_ref="tool.receipt.v1",
                )
            }

        if verdict == "deny":
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "denied",
                        "tool": tool_name,
                        "decision_id": decision_id,
                        "action_type": action_type,
                        "error": "grant denied",
                    },
                    schema_ref="tool.receipt.v1",
                )
            }

        if verdict != "allow":
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "error",
                        "decision_id": decision_id,
                        "action_type": action_type,
                        "error": f"unknown verdict: {verdict!r}",
                    },
                    schema_ref="tool.receipt.v1",
                )
            }

        tool_range = tuple(node.config.get("tools", ()) or ())
        lab = act_body.lab_tools()
        if effect_kind in _TOOL_KINDS and (
            tool_name in (None, "__none__") or not lab.contains(str(tool_name))
        ):
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "denied",
                        "tool": tool_name,
                        "decision_id": decision_id,
                        "action_type": action_type,
                        "error": f"tool not in registry: {tool_name!r}",
                    },
                    schema_ref="tool.receipt.v1",
                )
            }

        allowed = tool_range or lab.names()
        try:
            obs = act_body.run_body_act(content, allowed_tools=allowed)
        except ApprovalPendingError as pending:
            req = getattr(pending, "approval_request", None)
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "waiting_input",
                        "tool": tool_name if effect_kind in _TOOL_KINDS else None,
                        "decision_id": decision_id,
                        "action_type": action_type,
                        "error": str(pending),
                        "approval_request": (
                            req
                            if isinstance(req, dict)
                            else getattr(req, "__dict__", {"raw": repr(req)})
                        ),
                    },
                    schema_ref="tool.receipt.v1",
                )
            }
        except Exception as exc:
            return {
                out_port: Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "error",
                        "tool": tool_name if effect_kind in _TOOL_KINDS else None,
                        "decision_id": decision_id,
                        "action_type": action_type,
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
                    decision_id=str(decision_id),
                    action_type=action_type,
                    tool=str(tool_name) if tool_name not in (None, "__none__") else None,
                ),
                schema_ref="tool.receipt.v1",
            )
        }


def configure_registry(registry: ToolRegistry) -> None:
    """Boot: wire the YAML tool inventory into Body composition."""
    act_body.configure_lab_tools(registry)
    from agent_lab.nodes.tool.dispatch_tool.plugin import (
        configure_registry as _legacy_configure,
    )

    _legacy_configure(registry)


def _content(artifact: Any) -> dict[str, Any]:
    if artifact is None:
        return {}
    raw = getattr(artifact, "content", None)
    return raw if isinstance(raw, dict) else {}
