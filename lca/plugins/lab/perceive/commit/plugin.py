"""perceive.commit — Build ContextManifest + digest (Hub commit step).

worker: commit(*, trimmed_items) -> context_manifest
kind: TRANSFORMER
out_port: context_manifest
in: trimmed_items=trimmed_items
"""
from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.perceive.ops import commit_manifest


def commit(
    *,
    trimmed_items: Artifact | None,
) -> dict[str, Artifact]:
    """Build ContextManifest + digest (Hub commit step; no Session write)."""
    return commit_manifest(trimmed_items=trimmed_items)


__all__ = ["commit"]
