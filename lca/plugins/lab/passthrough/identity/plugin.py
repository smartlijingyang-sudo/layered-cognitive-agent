"""passthrough.identity — pass-through identity node.

worker: identity(*, inputs, from_port, to_port) -> to_port
kind: PASSTHROUGH
config: from_port to_port
"""
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def identity(
    *,
    inputs: dict[str, Artifact],
    from_port: str,
    to_port: str,
) -> dict[str, Artifact]:
    """把 ``from_port`` 端口的 Artifact 透传到 ``to_port``。"""
    src = inputs.get(from_port, Artifact(kind=ArtifactKind.TEXT, content=""))
    return {to_port: src}


__all__ = ["identity"]
