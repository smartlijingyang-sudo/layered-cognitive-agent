"""perceive.sense.memory — enrich state.retrieved_context via MemorySystem.

Single-responsibility: pull relevant memory items for the current state,
write them into state.retrieved_context. 1 input (state), 1 output (state).

Default: NullMemorySystem (returns nothing). Production profiles inject a
real MemorySystem via provider_config.memory_factory. Tests inject a
fixture via provider_config.fixture_memory_name.

Memory items come back as list[dict] with shape
  {kind: "...", payload: ..., provenance: ..., ref: ..., extra: ...}
mirroring LCA ContextItem. We write them into state.retrieved_context
verbatim; Hub reads them at fold time.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="perceive.sense.memory",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Query MemorySystem; write retrieved items into state.retrieved_context.",
    inputs=[PortInfo("state", kind=PortKind.FACT)],
    outputs=[PortInfo("state", kind=PortKind.FACT)],
)
class SenseMemory(Node):
    name = "perceive.sense.memory"

    def execute(self, node, inputs):
        from lca.contracts.atoms.enums.enums import MemoryLayer
        from lca.cognition.memory.simple.memory import SimpleMemorySystem

        state_a = inputs.get("state")
        if not state_a or not isinstance(state_a.content, dict):
            return {"state": state_a}

        base = dict(state_a.content)
        mem_sys = _resolve_memory(node.config)
        # Build minimal state for retrieve; reuse what's already there.
        try:
            # MemorySystem.query(layer) -> list[MemoryRecord]
            # We don't have a "user_input" layer; query the working layer.
            raw = mem_sys.query(MemoryLayer.WORKING) if hasattr(mem_sys, "query") else []
        except Exception:
            raw = []

        # Normalize to list-of-dicts (Hub expects ContextItem shape).
        items = []
        for it in (raw or []):
            if isinstance(it, dict):
                items.append(it)
            else:
                items.append({
                    "kind": getattr(it, "kind", ""),
                    "payload": getattr(it, "payload", None),
                    "provenance": getattr(it, "provenance", ""),
                    "ref": getattr(it, "ref", None),
                    "extra": dict(getattr(it, "extra", {}) or {}),
                })

        existing = base.get("retrieved_context") or []
        merged = list(existing) if isinstance(existing, list) else []
        merged.extend(items)
        base["retrieved_context"] = merged
        return {"state": Artifact(
            kind=ArtifactKind.FACT,
            content=base,
            schema_ref="agent_state.v1",
        )}


def _resolve_memory(config: dict):
    """Resolve a MemorySystem: fixture > factory > SimpleMemorySystem (empty default)."""
    cfg = config.get("provider_config") or {}
    name = cfg.get("fixture_memory_name")
    if name:
        try:
            from agent_lab.nodes.perceive.sense.memory import _fixtures
            f = _fixtures.FIXTURES.get(name)
            if f is not None:
                return f
        except ImportError:
            pass
    factory = cfg.get("memory_factory")
    if isinstance(factory, dict) and factory.get("ref"):
        ref = factory["ref"]
        kwargs = dict(factory.get("kwargs") or {})
        mod, _, attr = ref.partition(":")
        cls = getattr(__import__(mod, fromlist=[attr]), attr)
        return cls(**kwargs)
    from lca.cognition.memory.simple.memory import SimpleMemorySystem
    return SimpleMemorySystem()


def _coerce_state(content: dict):
    from lca.contracts.models.core.state.state import AgentState
    try:
        return AgentState(**{k: content.get(k) for k in
                              ("trace_id", "task", "budget", "step",
                               "working_memory", "retrieved_context",
                               "schema_version", "user_input",
                               "tool_results", "history", "extra")
                              if k in content})
    except Exception:
        return AgentState(trace_id="", task="", budget=None)
