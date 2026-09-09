"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.join
stage: control
kind: ROUTER
out_port: out
description: Join N parallel branch outputs into one artifact.

worker: join(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def join(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for join — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    out_port = node.outs[0]
    merged: dict = {}
    for k, a in inputs.items():
        merged[k] = a.content
    return {out_port: Artifact(kind=ArtifactKind.FACT, content=merged, schema_ref="join.merged.v1")}


__all__ = ["join"]
