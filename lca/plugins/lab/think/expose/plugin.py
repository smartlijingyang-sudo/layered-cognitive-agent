"""think.expose — committed ContextManifest → messages + tools.

worker: expose(*, in_assembled_manifest) -> messages + tools
kind: TRANSFORMER
out_port: messages
"""
from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.think.expose.ops import peel_manifest


def expose(
    *,
    in_assembled_manifest: Artifact | None,
) -> dict[str, Artifact]:
    """Peel frozen messages + tools from ContextManifest."""
    return peel_manifest(in_assembled_manifest)


__all__ = ["expose"]
