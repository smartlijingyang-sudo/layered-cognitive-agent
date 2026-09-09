"""act.observe — Receipt → ObservationManifest(single exit from act phase).

worker: observe(*, observation) -> ObservationManifest
kind: TRANSFORMER
out_port: observation
in: receipt=observation
"""
from dataclasses import dataclass
from typing import Any

from agent_lab.primitives.artifact import Artifact


@dataclass(frozen=True, slots=True)
class ObservationManifest:
    success: bool
    tool: str | None
    body_ref: str | None
    executed_via: str | None
    content_type: str


def observe(*, observation: Artifact | None) -> dict[str, Any]:
    """把 Receipt artifact 规整成 ObservationManifest 字典。"""
    content: dict[str, Any] = (
        dict(observation.content) if observation is not None and isinstance(observation.content, dict) else {}
    )
    return {
        "success": content.get("executed_via") is not None,
        "tool": content.get("tool"),
        "body_ref": content.get("body_ref"),
        "executed_via": content.get("executed_via"),
        "content_type": observation.kind.value if observation is not None else "text",
    }


__all__ = ["ObservationManifest", "observe"]
