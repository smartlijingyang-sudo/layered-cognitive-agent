# PR-D final 2/2 — reflect.extract real @plugin carrier
"""Real carrier for ``agent_lab.nodes.reflect.extract.plugin.ReflectExtract``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``ReflectExtract`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.reflect.extract``
Output capability: ``lab.reflect.extract.out:lesson``

delete-when (PR-D final 2/2):
- agent_lab/nodes/reflect/extract/plugin.py replaced by this carrier
  (test env: delete-when happens when LCA runtime with cordis
  is in place and the legacy plugin can be removed)
"""

from __future__ import annotations

from lca.plugins.lab.internal.hooks import (
    LabCarrier,
    bind_carrier,
)


# Carrier data: what the loader's register_carrier() needs.
_CARRIER = LabCarrier(
    id="lab.reflect.extract",
    stage="reflect",
    kind="TRANSFORMER",
    description='Extract a lesson from the critique.',
    node_id='extract',
    source_module='agent_lab.nodes.reflect.extract.plugin',
    source_class='ReflectExtract',
    provides=['reflect_lesson'],
    requires=[],
    emits=['reflect_lesson'],
    inputs=[('critique', 'FACT', False)],
    outputs=[('lesson', 'FACT')],
    out_capabilities=['lab.reflect.extract.out:lesson'],
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


# Auto-bind on import so the loader walks these like any other plugin
# carrier — the setup() function is still callable from a real Cordis
# boot path for two-phase register.
bind_carrier(_CARRIER)


__all__ = ["setup", "_CARRIER"]

# --- PR-D worker execute -----------------------------------------------
from lca.plugins.lab.internal.worker import Worker, register_worker
from agent_lab.primitives.artifact import Artifact, ArtifactKind

def _candidates_from_reflection(content):
    candidates = []
    reflection_id = content.get("reflection_id", "")
    lesson = content.get("lesson")
    if lesson:
        candidates.append({"kind": "lesson", "verdict": content.get("verdict", ""), "text": lesson, "reflection_id": reflection_id})
    correction = content.get("correction")
    if isinstance(correction, dict) and correction:
        candidates.append({"kind": "correction", "decision_id": correction.get("decision_id", ""), "action_type": correction.get("action_type", ""), "reflection_id": reflection_id})
    extra = content.get("extra")
    if isinstance(extra, dict) and extra:
        candidates.append({"kind": "extra", "payload": extra, "reflection_id": reflection_id})
    return candidates

from agent_lab.primitives.artifact import Artifact, ArtifactKind

class _Reflect_Extract(Worker):
    factory = "reflect.extract"

    def execute(self, node, inputs, seams=None):
        src = (getattr(node, "config", None) or {}).get("from", "reflection")
        reflection_artifact = inputs.get(src) or inputs.get("reflection")
        content = {}
        if reflection_artifact is not None and isinstance(reflection_artifact.content, dict):
            content = dict(reflection_artifact.content)
        candidates = _candidates_from_reflection(content)
        reflection_out = Artifact(
            kind=ArtifactKind.FACT,
            content=content,
            schema_ref=getattr(reflection_artifact, "schema_ref", None) or "reflection.v1",
        )
        memory_candidates = Artifact(
            kind=ArtifactKind.FACT,
            content={"items": candidates},
            schema_ref="memory.candidates.v1",
        )
        reflect_signal = Artifact(
            kind=ArtifactKind.FACT,
            content={"reflection_id": content.get("reflection_id", ""), "verdict": content.get("verdict", ""), "candidate_count": len(candidates)},
            schema_ref="reflect.signal.v1",
        )
        return {"reflection_out": reflection_out, "memory_candidates": memory_candidates, "reflect_signal": reflect_signal}

register_worker("reflect.extract", _Reflect_Extract)
register_worker("lab.reflect.extract", _Reflect_Extract)
