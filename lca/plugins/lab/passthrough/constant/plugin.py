"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.passthrough.constant
stage: passthrough
kind: PASSTHROUGH
out_port: out
description: Emit a constant value.

worker: constant(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def constant(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for constant — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    dst = node.outs[0]
    return {
        dst: make_text(
            str(node.config.get("value", "")),
            schema_ref=node.config.get("schema_ref", "raw"),
        )
    }


__all__ = ["constant"]
