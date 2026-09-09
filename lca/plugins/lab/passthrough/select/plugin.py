"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.passthrough.select
stage: passthrough
kind: PASSTHROUGH
out_port: out
description: Select a field from the input.

worker: select(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def select(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for select — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    src = node.config.get("key", node.ins[0])
    dst = node.config.get("to", node.outs[0])
    if src not in inputs:
        return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
    return {dst: inputs[src]}


__all__ = ["select"]
