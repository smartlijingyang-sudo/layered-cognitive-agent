"""Tool nodes — build intent, dispatch, write receipt.

Tool dispatch is mocked via the in-process `_TOOL_REGISTRY`.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_TOOL_REGISTRY: dict[str, callable] = {}  # name -> callable(intent_dict) -> result_str
_BODY_PROVIDERS: dict[str, object] = {}  # name -> LcaBodyProvider (lazy)


def register_tool(name: str, fn) -> None:
    _TOOL_REGISTRY[name] = fn


def register_body_provider(name: str, provider) -> None:
    _BODY_PROVIDERS[name] = provider


def _default_body_provider() -> object:
    if "default" not in _BODY_PROVIDERS:
        from agent_lab.adapters.lca_body import LcaBodyProvider

        _BODY_PROVIDERS["default"] = LcaBodyProvider()
    return _BODY_PROVIDERS["default"]


@node(
    id="build_intent",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.PRODUCER,
    description="Combine tool name (config) + args into a structured ToolIntent artifact.",
    inputs=[PortInfo("args", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("intent", kind=PortKind.INTENT)],
    provides=["tool_intent"],
    consumes=[],
    emits=["tool_intent"],
    relates_to=["grant_check", "dispatch_tool"],
)
class BuildIntent(Node):
    """Combine model intent (text) + context into a structured ToolIntent artifact."""

    name = "build_intent"

    def execute(self, node, inputs):
        tool_name = node.config["tool"]
        args_a = inputs.get("args")
        out_port = node.config.get("to", "intent")
        args = args_a.content if args_a else {}
        return {out_port: Artifact(
            kind=ArtifactKind.INTENT,
            content={"tool": tool_name, "args": args},
            schema_ref="tool.intent.v1",
        )}


@node(
    id="grant_check",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.VALIDATOR,
    description="Static allowlist check (config.allow:[str]). No business logic.",
    inputs=[PortInfo("intent", kind=PortKind.INTENT, required=False)],
    outputs=[PortInfo("verdict", kind=PortKind.VERDICT)],
    provides=["grant_verdict"],
    consumes=["tool_intent"],
    relates_to=["build_intent", "dispatch_tool", "route_on"],
)
class GrantCheck(Node):
    """Static allowlist check (config.allow:[str]). No business logic."""

    name = "grant_check"

    def execute(self, node, inputs):
        allow = set(node.config.get("allow", []))
        intent_a = inputs.get("intent")
        out_port = node.config.get("to", "verdict")
        tool = intent_a.content.get("tool") if intent_a else None
        verdict = "allow" if tool in allow else "deny"
        return {out_port: Artifact(kind=ArtifactKind.FACT, content={"verdict": verdict, "tool": tool}, schema_ref="grant.verdict.v1")}


@node(
    id="dispatch_tool",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.EXECUTOR,
    description="Invoke the tool from the in-process registry. Mock-safe.",
    inputs=[PortInfo("routed", kind=PortKind.INTENT, required=False)],
    outputs=[PortInfo("receipt", kind=PortKind.RECEIPT)],
    provides=["effect_receipt"],
    consumes=["tool_intent"],
    emits=["effect_receipt"],
    relates_to=["grant_check", "write_receipt", "integrate_observation"],
)
class DispatchTool(Node):
    """Invoke the tool from the in-process registry. Mock-safe."""

    name = "dispatch_tool"

    def execute(self, node, inputs):
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
        # Provider selection: "lca" -> LcaBodyProvider (real executor);
        # "default" or missing -> in-process _TOOL_REGISTRY.
        provider_name = node.config.get("provider", "default")
        if provider_name == "lca" or (provider_name not in _TOOL_REGISTRY and _BODY_PROVIDERS):
            provider = _BODY_PROVIDERS.get(provider_name) or _default_body_provider()
            return {out_port: provider.to_receipt_artifact(tool, args, port=out_port)}
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
        except Exception as exc:
            return {out_port: Artifact(
                kind=ArtifactKind.RECEIPT,
                content={"status": "error", "tool": tool, "error": str(exc)},
                schema_ref="tool.receipt.v1",
            )}


@node(
    id="write_receipt",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.PASSTHROUGH,
    description="Pass-through the receipt; this is a hook point for journaling later.",
    inputs=[PortInfo("receipt", kind=PortKind.RECEIPT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.RECEIPT)],
    provides=["receipt_fact"],
    consumes=["effect_receipt"],
    relates_to=["dispatch_tool", "integrate_observation"],
)
class WriteReceipt(Node):
    """Pass-through the receipt; this is a hook point for journaling later."""

    name = "write_receipt"

    def execute(self, node, inputs):
        src = node.config.get("from", "receipt")
        out_port = node.config.get("to", "receipt_fact")
        return {out_port: inputs[src] if src in inputs else Artifact(kind=ArtifactKind.RECEIPT, content={})}


@node(
    id="integrate_observation",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.TRANSFORMER,
    description="Convert a receipt into a model-visible observation artifact.",
    inputs=[PortInfo("receipt_fact", kind=PortKind.RECEIPT, required=False)],
    outputs=[PortInfo("observation", kind=PortKind.TEXT)],
    provides=["observation"],
    consumes=["effect_receipt"],
    relates_to=["dispatch_tool", "write_receipt", "merge_messages"],
)
class IntegrateObservation(Node):
    """Convert a receipt into a model-visible observation artifact."""

    name = "integrate_observation"

    def execute(self, node, inputs):
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
