"""expose ops — peel messages from a committed ContextManifest."""

from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def peel_messages(manifest_artifact: Artifact | None) -> Artifact:
    if manifest_artifact is None:
        raise ValueError("think.expose: missing ContextManifest input")

    content = manifest_artifact.content
    if not isinstance(content, dict):
        raise ValueError(
            f"think.expose: ContextManifest content must be dict, got {type(content).__name__}"
        )
    if content.get("committed") is not True:
        raise ValueError(
            "think.expose: ContextManifest is not committed; "
            "refuse to feed an unfrozen view to reason"
        )
    raw_messages = content.get("messages")
    if not isinstance(raw_messages, list):
        raise ValueError("think.expose: ContextManifest.messages missing or not a list")

    messages: list[dict[str, Any]] = [dict(m) for m in raw_messages if isinstance(m, dict)]
    return Artifact(
        kind=ArtifactKind.MESSAGE,
        content=messages,
        schema_ref="openai.messages.v1",
    )
