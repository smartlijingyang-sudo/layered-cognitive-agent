"""dispatch_tool node — resolve a Tool by name from a ToolRegistry, then run it.

Provider selection is data, not code.  Two layers of configuration:

  1. ``tools:`` (a list of tool names) is the *range* this dispatch node
     is allowed to invoke.  It is checked against the registry at provider
     init time and forwarded to ``LcaBodyProvider(tool_range=...)``.
  2. The provider is created per-node by ``LcaBodyProvider`` using the
     registry supplied by the runner.

If the routed intent's tool name is outside the declared range, the
provider returns ``{"status": "denied", "error": ...}`` and the rest of
the chain (write_receipt / integrate) handles the denial normally.
"""

from __future__ import annotations

import importlib

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_DEFAULT_PROVIDER_KINDS: dict[str, str] = {
    "lca": "agent_lab.adapters.lca_body:LcaBodyProvider",
}


def _resolve_provider(node, *, tool_registry):
    """Build an LcaBodyProvider bound to this node's tool range.

    ``node.config`` keys consumed:
      - ``provider_ref``    : ``module:Class`` for the provider
      - ``provider_kind``   : ``"lca"`` shorthand
      - ``provider_config`` : opaque kwargs to the provider
      - ``tools``           : list[str] tool range (REQUIRED for clarity;
                              without it the provider falls back to
                              "everything in the registry", which is fine
                              for ad-hoc scripts but never for declared graphs)
    """
    cfg = node.config or {}
    provider_ref = cfg.get("provider_ref")
    provider_kind = cfg.get("provider_kind")
    if provider_ref is None and provider_kind is not None:
        provider_ref = _DEFAULT_PROVIDER_KINDS.get(provider_kind)
    if provider_ref is None:
        raise RuntimeError(
            f"dispatch_tool node '{node.id}' missing 'provider_ref' or 'provider_kind'"
        )
    module_name, _, class_name = provider_ref.partition(":")
    module = importlib.import_module(module_name)
    provider_cls = getattr(module, class_name)
    provider_config = dict(cfg.get("provider_config", {}) or {})
    # Range wins over provider_config["tools"] (single source of truth).
    tool_range = tuple(cfg.get("tools", provider_config.pop("tools", ())) or ())
    return provider_cls(tool_registry=tool_registry, tool_range=tool_range)


@node(
    id="dispatch_tool",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.EXECUTOR,
    description=(
        "Dispatch a tool via an LcaBodyProvider bound to a named range from "
        "the agent_lab ToolRegistry. Range is declared in node.config.tools: "
        "and resolved against registry names at provider init."
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
        registry = _registry()
        provider = _resolve_provider(node, tool_registry=registry)
        if not hasattr(provider, "to_receipt_artifact"):
            raise RuntimeError(
                f"dispatch_tool node '{node.id}': provider {type(provider).__name__} "
                "has no .to_receipt_artifact() method"
            )
        return {out_port: provider.to_receipt_artifact(tool, args, port=out_port)}


# ---------------------------------------------------------------------------
# Singleton ToolRegistry — loaded lazily from agent_lab/tools/registry.yaml.
# The runner is responsible for eagerly calling ``_registry.load(...)`` at
# boot; ``_registry()`` here is the dispatcher-side accessor.
# ---------------------------------------------------------------------------

_REGISTRY_SINGLETON: dict[str, object] = {}


def configure_registry(registry) -> None:
    """Set the singleton registry.  Called by the runner at boot."""
    _REGISTRY_SINGLETON["value"] = registry


def _registry():
    from agent_lab.tools import ToolRegistry

    registry = _REGISTRY_SINGLETON.get("value")
    if registry is None:
        # Auto-load on first use so ad-hoc scripts still work.
        registry = ToolRegistry()
        registry.load_from_yaml(_default_registry_path())
        _REGISTRY_SINGLETON["value"] = registry
    return registry


def _default_registry_path():
    from pathlib import Path

    return Path(__file__).resolve().parents[3] / "tools" / "registry.yaml"
