"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.passthrough.rank
stage: passthrough
kind: PASSTHROUGH
out_port: out
description: Rank the input list.

worker: rank(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def rank(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for rank — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    src = node.config.get("from", node.ins[0])
    dst = node.config.get("to", node.outs[0])
    keep = int(node.config.get("keep", 50))
    split_on = node.config.get("split_on", "\n")
    src_a = inputs.get(src)
    if src_a is None:
        return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
    text = str(src_a.content)
    parts = [p for p in text.split(split_on) if p][:keep]
    return {
        dst: Artifact(kind=ArtifactKind.TEXT, content=split_on.join(parts), schema_ref="ranked.v1")
    }


__all__ = ["rank"]
