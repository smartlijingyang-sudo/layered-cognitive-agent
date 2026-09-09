"""remember.admit — Decide which memory candidates to admit.

worker: admit(*, in_observation, in_candidates, provider_config) -> admitted
kind: TRANSFORMER
out_port: admitted
config: provider_config
"""
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

from lca.plugins.lab.control.ops import LcaControlRememberAdmitProvider


def _items_from_candidates(art: Artifact | None) -> list[dict[str, Any]]:
    """Extract item list from memory_candidates artifact (None → [])."""
    if art is None:
        return []
    content = getattr(art, "content", None)
    if not isinstance(content, dict):
        return []
    items = content.get("items")
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


def admit(
    *,
    in_observation: Artifact | None,
    in_candidates: Artifact | None,
    provider_config: dict[str, Any] | None = None,
) -> dict[str, Artifact]:
    """由 provider_config 决定 admit,合并 candidates。"""
    provider = LcaControlRememberAdmitProvider.from_node_config(provider_config or {})
    verdict = provider.admit(observation=in_observation, out_port="admit_verdict")
    verdict_art = verdict.get("admit_verdict")
    admitted_flag = bool(
        verdict_art.content.get("admitted")
        if verdict_art is not None and isinstance(verdict_art.content, dict)
        else False
    )
    items = _items_from_candidates(in_candidates) if admitted_flag else []
    return {
        "admitted": Artifact(
            kind=ArtifactKind.FACT,
            content={"admitted": admitted_flag, "items": items},
            schema_ref="memory.admitted.v1",
        )
    }


__all__ = ["admit"]
