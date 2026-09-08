"""perceive.sense.memory.resolve — resolve a MemorySystem instance.

Pure factory node: takes node.config, returns an Artifact wrapping a
resolved MemorySystem (LCA contracts/protocols/memory Protocol).
This is the seam (ADR-0195 §1.4 C13 information lineage closure).

Resolution order:
  1. fixture_memory_name (test-only)
  2. memory_factory {ref: "module:Class", kwargs: {...}} (production)
  3. SimpleMemorySystem() (empty default, requires only contracts)

Per ADR-0191 DSH: this node owns NO facts; MemorySystem is queried as
a read-only projection. No state mutation, no Session access.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="perceive.sense.memory.resolve",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Resolve a MemorySystem instance from node.config (fixture > factory > SimpleMemorySystem default).",
    inputs=[],
    outputs=[PortInfo("memory_system", kind=PortKind.ARTIFACT)],
)
class ResolveMemory(Node):
    name = "perceive.sense.memory.resolve"

    def execute(self, node, inputs):
        mem_sys = _resolve(node.config)
        return {"memory_system": Artifact(
            kind=ArtifactKind.FACT,
            content=mem_sys,
            schema_ref="memory.system.v1",
        )}


def _resolve(config: dict):
    """Resolve a MemorySystem: fixture > factory > SimpleMemorySystem (empty default)."""
    cfg = config.get("provider_config") or {}
    name = cfg.get("fixture_memory_name")
    if name:
        try:
            from agent_lab.nodes.perceive.sense.memory import _fixtures
        except ImportError:
            _fixtures = None  # type: ignore[assignment]
        if _fixtures is not None:
            f = _fixtures.FIXTURES.get(name)
            if f is not None:
                return f
    factory = cfg.get("memory_factory")
    if isinstance(factory, dict) and factory.get("ref"):
        ref = factory["ref"]
        kwargs = dict(factory.get("kwargs") or {})
        mod, _, attr = ref.partition(":")
        cls = getattr(__import__(mod, fromlist=[attr]), attr)
        return cls(**kwargs)
    from lca.cognition.memory.simple.memory import SimpleMemorySystem
    return SimpleMemorySystem()
