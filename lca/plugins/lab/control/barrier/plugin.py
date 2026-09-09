"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.barrier
stage: control
kind: ROUTER
out_port: out
description: Single-slot pass-through (BSP barrier lives in runtime scheduler).

worker: barrier(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def barrier(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for barrier — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    from agent_lab.primitives.artifact import Artifact, ArtifactKind
    src = node.config.get("from", node.ins[0])
    dst = node.config.get("to", node.outs[0])
    return {dst: inputs.get(src, Artifact(kind=ArtifactKind.TEXT, content=""))}


__all__ = ["barrier"]
