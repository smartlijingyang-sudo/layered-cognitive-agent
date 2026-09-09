"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.discard
stage: control
kind: PRODUCER
out_port: out
description: Discard an output (sink only).

worker: discard(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def discard(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for discard — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    from agent_lab.primitives.artifact import Artifact, ArtifactKind
    src = node.config.get("from", node.ins[0])
    out_port = node.config.get("to", node.outs[0])
    src_a = inputs.get(src)
    return {out_port: Artifact(kind=ArtifactKind.FACT, content={"discarded": True, "digest": src_a.short_id() if src_a else None}, schema_ref="discard.v1")}


__all__ = ["discard"]
