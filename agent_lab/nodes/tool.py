"""Tool nodes — build intent, dispatch, write receipt.

Tool dispatch reads its provider from ``node.config``:
  - ``provider_ref``: dotted ``module:Class`` path to a provider class that
    accepts ``register_tool(...)`` and exposes ``to_receipt_artifact(name,
    args, port) -> Artifact``. See ``agent_lab.adapters.lca_body.LcaBodyProvider``.
  - ``provider_kind``: optional ``"lca"`` / ``"mock"`` shorthand.
  - ``provider_config``: opaque dict passed to the provider constructor.

No global registry. The graph config IS the dispatch backend.
"""

from __future__ import annotations

import importlib

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_DEFAULT_PROVIDER_KINDS: dict[str, str] = {
    "lca": "agent_lab.adapters.lca_body:LcaBodyProvider",
}


def _resolve_provider(node):
    """Read provider factory from node.config and instantiate it.

    Resolution order:
      1. ``provider_ref`` (module:Class) -> import + instantiate(**provider_config)
      2. ``provider_kind`` ('lca' | 'mock') -> map to default ``provider_ref``
      3. raise ConfigurationError
    """
    cfg = node.config or {}
    provider_ref = cfg.get("provider_ref")
    provider_kind = cfg.get("provider_kind")
    if provider_ref is None and provider_kind is not None:
        provider_ref = _DEFAULT_PROVIDER_KINDS.get(provider_kind)
    if provider_ref is None:
        raise RuntimeError(
            f"dispatch_tool node '{node.id}' missing 'provider_ref' or 'provider_kind' in config"
        )
    module_name, _, class_name = provider_ref.partition(":")
    if not module_name or not class_name:
        raise RuntimeError(
            f"dispatch_tool node '{node.id}': provider_ref must be 'module:Class', got {provider_ref!r}"
        )
    module = importlib.import_module(module_name)
    provider_cls = getattr(module, class_name)
    provider_config = cfg.get("provider_config", {}) or {}
    return provider_cls(**provider_config)


def _register_default_tools(provider) -> None:
    """If the provider exposes register_tool, register two in-process tools.

    These are demo tools (echo, calc) used when dispatch_tool has no
    provider_config.tools entries. Real apps pass their own ToolShim
    instances via provider_config.
    """
    if not hasattr(provider, "register_tool"):
        return
    from agent_lab.adapters.lca_body import ToolShim

    def _echo(args):
        return f"echo({args})"

    def _calc(args):
        expr = str(args.get("expr", "0"))
        return str(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307 — demo only

    provider.register_tool(ToolShim(
        name="echo",
        description="Echo the args back as text.",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
        is_idempotent=True,
        effect_kind="ephemeral",
        default_timeout_s=5,
        _callable=_echo,
    ))
    provider.register_tool(ToolShim(
        name="calc",
        description="Evaluate a python arithmetic expression.",
        parameters={"type": "object", "properties": {"expr": {"type": "string"}}},
        is_idempotent=True,
        effect_kind="ephemeral",
        default_timeout_s=5,
        _callable=_calc,
    ))


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
    description=(
        "Dispatch the tool via a provider loaded from node.config "
        "(provider_ref or provider_kind). Provider is instantiated per-node "
        "on each execute(); no global registry."
    ),
    inputs=[PortInfo("routed", kind=PortKind.INTENT, required=False)],
    outputs=[PortInfo("receipt", kind=PortKind.RECEIPT)],
    provides=["effect_receipt"],
    consumes=["tool_intent"],
    emits=["effect_receipt"],
    relates_to=["grant_check", "write_receipt", "integrate_observation"],
)
class DispatchTool(Node):
    """Dispatch the tool via the configured provider; return receipt."""

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
        provider = _resolve_provider(node)
        # Auto-register the demo ToolShims if provider supports it and
        # the user didn't pre-populate tools via provider_config.
        if hasattr(provider, "register_tool"):
            existing = getattr(provider, "_tools", {}) or {}
            if not existing:
                _register_default_tools(provider)
        # providers must implement to_receipt_artifact(name, args, port) -> Artifact
        if not hasattr(provider, "to_receipt_artifact"):
            raise RuntimeError(
                f"dispatch_tool node '{node.id}': provider {type(provider).__name__} "
                "has no .to_receipt_artifact() method"
            )
        return {out_port: provider.to_receipt_artifact(tool, args, port=out_port)}


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
