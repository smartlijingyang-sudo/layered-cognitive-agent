"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.passthrough.select_v2
stage: passthrough
kind: PASSTHROUGH
out_port: out
description: Select v2.

worker: passthrough__select(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def passthrough__select(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for passthrough__select — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    in_a = inputs.get("in")
    field = node.config.get("field", "")
    content = in_a.content if in_a else {}
    if isinstance(content, dict):
        return {"out": content.get(field)}
    return {"out": Artifact(kind=ArtifactKind.TEXT, content="")}


__all__ = ["passthrough__select"]
