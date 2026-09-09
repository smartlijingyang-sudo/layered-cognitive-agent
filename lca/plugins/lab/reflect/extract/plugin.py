"""reflect.extract — Reflection → reflection_out + memory_candidates + reflect_signal.

worker: extract(*, reflection) -> reflection_out + memory_candidates + reflect_signal
kind: TRANSFORMER
out_port: reflection_out
"""
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def _candidates_from_reflection(content: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract lesson / correction / extra memory candidates from reflection content."""
    candidates: list[dict[str, Any]] = []
    reflection_id = content.get("reflection_id", "")
    lesson = content.get("lesson")
    if lesson:
        candidates.append(
            {"kind": "lesson", "verdict": content.get("verdict", ""),
             "text": lesson, "reflection_id": reflection_id}
        )
    correction = content.get("correction")
    if isinstance(correction, dict) and correction:
        candidates.append(
            {"kind": "correction", "decision_id": correction.get("decision_id", ""),
             "action_type": correction.get("action_type", ""),
             "reflection_id": reflection_id}
        )
    extra = content.get("extra")
    if isinstance(extra, dict) and extra:
        candidates.append(
            {"kind": "extra", "payload": extra, "reflection_id": reflection_id}
        )
    return candidates


def extract(
    *,
    reflection: Artifact | None,
) -> dict[str, Artifact]:
    """从 reflection artifact 抽出 reflection_out / memory_candidates / reflect_signal。"""
    content: dict[str, Any] = (
        dict(reflection.content) if reflection is not None and isinstance(reflection.content, dict) else {}
    )
    candidates = _candidates_from_reflection(content)
    return {
        "reflection_out": Artifact(
            kind=ArtifactKind.FACT,
            content=content,
            schema_ref=getattr(reflection, "schema_ref", None) or "reflection.v1",
        ),
        "memory_candidates": Artifact(
            kind=ArtifactKind.FACT,
            content={"items": candidates},
            schema_ref="memory.candidates.v1",
        ),
        "reflect_signal": Artifact(
            kind=ArtifactKind.FACT,
            content={
                "reflection_id": content.get("reflection_id", ""),
                "verdict": content.get("verdict", ""),
                "candidate_count": len(candidates),
            },
            schema_ref="reflect.signal.v1",
        ),
    }


__all__ = ["extract"]
