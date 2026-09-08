"""Tool nodes — build intent, dispatch, write receipt.

Tool dispatch is mocked via the in-process `_TOOL_REGISTRY`.
"""

from __future__ import annotations

from agent_lab.graph.spec import InfoNode
from agent_lab.nodes.base import Node, register
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_TOOL_REGISTRY: dict[str, callable] = {}  # name -> callable(intent_dict) -> result_str


def register_tool(name: str, fn) -> None:
    _TOOL_REGISTRY[name] = fn


@register
class BuildIntent(Node):
    """Combine model intent (text) + context into a structured ToolIntent artifact."""

    name = "build_intent"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        tool_name = node.config["tool"]
        args_a = inputs.get("args")
        out_port = node.config.get("to", "intent")
        args = args_a.content if args_a else {}
        return {out_port: Artifact(
            kind=ArtifactKind.INTENT,
            content={"tool": tool_name, "args": args},
            schema_ref="tool.intent.v1",
        )}


@register
class GrantCheck(Node):
    """Static allowlist check (config.allow:[str]). No business logic."""

    name = "grant_check"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        allow = set(node.config.get("allow", []))
        intent_a = inputs.get("intent")
        out_port = node.config.get("to", "verdict")
        tool = intent_a.content.get("tool") if intent_a else None
        verdict = "allow" if tool in allow else "deny"
        return {out_port: Artifact(kind=ArtifactKind.FACT, content={"verdict": verdict, "tool": tool}, schema_ref="grant.verdict.v1")}


@register
class DispatchTool(Node):
    """Invoke the tool from the in-process registry. Mock-safe."""

    name = "dispatch_tool"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        intent_port = node.config.get("from", "intent")
        out_port = node.config.get("to", "receipt")
        intent_a = inputs.get(intent_port)
        if intent_a is None or intent_a.content.get("verdict") == "deny":
            return {out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content={"status": "denied"},
                schema_ref="tool.receipt.v1",
            )}
        tool = intent_a.content.get("tool")
        if tool in (None, "__none__"):
            return {out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content={"status": "denied"},
                schema_ref="tool.receipt.v1",
            )}
        args = intent_a.content.get("args", {})
        fn = _TOOL_REGISTRY.get(tool)
        if fn is None:
            return {out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content={"status": "error", "error": f"tool {tool} not registered"},
                schema_ref="tool.receipt.v1",
            )}
        try:
            result = fn(args)
            return {out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content={"status": "ok", "tool": tool, "result": result},
                schema_ref="tool.receipt.v1",
            )}
        except Exception as exc:  # surface as receipt error (deterministic boundary)
            return {out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content={"status": "error", "tool": tool, "error": str(exc)},
                schema_ref="tool.receipt.v1",
            )}


@register
class WriteReceipt(Node):
    """Pass-through the receipt; this is a hook point for journaling later."""

    name = "write_receipt"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        src = node.config.get("from", "receipt")
        out_port = node.config.get("to", "receipt_fact")
        return {out_port: inputs[src] if src in inputs else Artifact(kind=ArtifactKind.RECEIPT, content={})}


@register
class IntegrateObservation(Node):
    """Convert a receipt into a model-visible observation artifact."""

    name = "integrate_observation"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        src = node.config.get("from", "receipt")
        out_port = node.config.get("to", "observation")
        rcpt = inputs.get(src)
        if rcpt is None:
            return {out_port: Artifact(kind=ArtifactKind.TEXT, content="")}
        text = ""
        if rcpt.content.get("status") == "ok":
            text = f"[tool:{rcpt.content.get('tool')}] {rcpt.content.get('result', '')}"
        else:
            text = f"[tool-error] {rcpt.content.get('error') or rcpt.content.get('status')}"
        return {out_port: Artifact(kind=ArtifactKind.TEXT, content=text, schema_ref="observation.v1")}
