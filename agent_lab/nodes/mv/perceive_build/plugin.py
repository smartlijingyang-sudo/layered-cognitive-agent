"""perceive_build node — call Hub.perceive(state) directly, freeze ContextManifest.

Fusion refactor (2026-09-08): removed LcaPerceiveProvider + register_fixture_hub
adapter layer. This node now:
  1. Resolves a PerceiveHub from node.config (factory ref or NullPerceiveHub)
  2. Coerces the state artifact into an LCA AgentState
  3. Calls hub.perceive(state) and wraps the frozen ContextManifest

Test fixtures: tests register Hubs via the same _FIXTURE_HUBS dict exposed
by this module (still process-local; no fixture code in production paths).
"""

from __future__ import annotations

import asyncio
from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import (
    NodeKind,
    NodeLayer,
    PortInfo,
    PortKind,
    node,
)
from agent_lab.primitives.artifact import Artifact, ArtifactKind

# Process-local fixture Hub registry (test-only path; keeps node.config
# JSON-serializable for plan_hash dump).
_FIXTURE_HUBS: dict[str, Any] = {}


def register_fixture_hub(name: str, hub: Any) -> None:
    """Register a Hub under ``name`` for later resolution by config."""
    _FIXTURE_HUBS[name] = hub


def unregister_fixture_hub(name: str) -> None:
    _FIXTURE_HUBS.pop(name, None)


def _resolve_hub(config: dict[str, Any]) -> Any:
    """Resolve a PerceiveHub from the node's provider_config block."""
    cfg = config.get("provider_config") or {}
    name = cfg.get("fixture_hub_name")
    if name and name in _FIXTURE_HUBS:
        return _FIXTURE_HUBS[name]
    factory = cfg.get("hub_factory")
    if isinstance(factory, dict) and factory.get("ref"):
        ref = factory["ref"]
        kwargs = dict(factory.get("kwargs") or {})
        mod, _, attr = ref.partition(":")
        cls = getattr(__import__(mod, fromlist=[attr]), attr)
        return cls(**kwargs)
    # Default: NullPerceiveHub (always works, requires only contracts).
    from lca.plugins.composer.runtime.fixture.runtime_factory import NullPerceiveHub
    return NullPerceiveHub()


def _coerce_state(artifact: Artifact | None) -> Any:
    """Coerce an agent_lab state artifact into an LCA AgentState."""
    from lca.contracts.models.core.state.state import AgentState

    content = (artifact.content if artifact is not None else None) or {}
    if not isinstance(content, dict):
        content = {}
    extra = dict(content.get("extra") or {})
    known = {"step", "history", "retrieved_context", "working_memory", "schema_version"}
    for k, v in content.items():
        if k not in known and k != "extra":
            extra[k] = v
    return AgentState(
        trace_id="",
        task="",
        budget=None,
        step=int(content.get("step", 0) or 0),
        retrieved_context=tuple(content.get("retrieved_context") or ()),
        extra=extra,
    )


def _item_to_dict(item: Any) -> dict[str, Any]:
    return {
        "kind": getattr(item, "kind", ""),
        "payload": getattr(item, "payload", None),
        "provenance": getattr(item, "provenance", ""),
        "ref": getattr(item, "ref", None),
        "extra": dict(getattr(item, "extra", {}) or {}),
    }


@node(
    id="perceive_build",
    name="perceive_build",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Resolve a PerceiveHub from node.config, call Hub.perceive(state) "
        "on the AgentState coerced from the state artifact, and emit a frozen "
        "ContextManifest as a MANIFEST artifact."
    ),
    inputs=[
        PortInfo("sanitized", kind=PortKind.ARTIFACT, required=False),
        PortInfo("state", kind=PortKind.ARTIFACT, required=False),
    ],
    outputs=[PortInfo("manifest", kind=PortKind.MANIFEST)],
    provides=["perceive_manifest"],
    requires=["perceive_hub"],
    emits=["context_manifest"],
    relates_to=["trust_classify", "dedup", "rank", "redact"],
)
class PerceiveBuild(Node):
    """Call Hub.perceive(state) directly; emit frozen ContextManifest."""

    name = "perceive_build"

    def execute(self, node, inputs):
        hub = _resolve_hub(node.config)
        out_port = node.config.get("to", node.outs[0] if node.outs else "manifest")
        state = _coerce_state(inputs.get("state"))
        manifest = asyncio.run(hub.perceive(state))
        return {out_port: Artifact(
            kind=ArtifactKind.MANIFEST,
            content={
                "items": [_item_to_dict(item) for item in manifest.items],
                "digest": manifest.digest,
                "schema_version": manifest.schema_version,
                "extra": dict(manifest.extra or {}),
            },
            schema_ref="context.manifest.v1",
        )}
