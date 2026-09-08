"""reflect.extract — Reflection → memory candidates + barrier signal.

Pure transform. Produces proposals for remember; never calls
MemorySystem.update or Session.append.
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


def _candidates_from_reflection(content: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive memory-candidate items from a Reflection dict."""
    candidates: list[dict[str, Any]] = []
    reflection_id = content.get("reflection_id", "")
    lesson = content.get("lesson")
    if lesson:
        candidates.append(
            {
                "kind": "lesson",
                "verdict": content.get("verdict", ""),
                "text": lesson,
                "reflection_id": reflection_id,
            }
        )
    correction = content.get("correction")
    if isinstance(correction, dict) and correction:
        candidates.append(
            {
                "kind": "correction",
                "decision_id": correction.get("decision_id", ""),
                "action_type": correction.get("action_type", ""),
                "reflection_id": reflection_id,
            }
        )
    extra = content.get("extra")
    if isinstance(extra, dict) and extra:
        candidates.append(
            {
                "kind": "extra",
                "payload": extra,
                "reflection_id": reflection_id,
            }
        )
    return candidates


@node(
    id="reflect.extract",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Extract memory candidates (lesson / correction / extra) from a "
        "Reflection and emit reflect_signal. No durable write."
    ),
    inputs=[PortInfo("reflection", kind=PortKind.FACT, required=False)],
    outputs=[
        PortInfo("reflection_out", kind=PortKind.FACT),
        PortInfo("memory_candidates", kind=PortKind.FACT),
        PortInfo("reflect_signal", kind=PortKind.FACT),
    ],
    provides=["reflection_out", "memory_candidates", "reflect_signal"],
    emits=["reflect_signal"],
    relates_to=["reflect.critique"],
)
class ReflectExtract(Node):
    name = "reflect.extract"

    def execute(self, node, inputs):
        src = (getattr(node, "config", None) or {}).get("from", "reflection")
        reflection_artifact = inputs.get(src) or inputs.get("reflection")
        content: dict[str, Any] = {}
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
            content={
                "reflection_id": content.get("reflection_id", ""),
                "verdict": content.get("verdict", ""),
                "candidate_count": len(candidates),
            },
            schema_ref="reflect.signal.v1",
        )
        return {
            "reflection_out": reflection_out,
            "memory_candidates": memory_candidates,
            "reflect_signal": reflect_signal,
        }
