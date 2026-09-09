"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.passthrough.identity_v2
stage: passthrough
kind: PASSTHROUGH
out_port: out
description: Identity v2 with extra typing.

worker: passthrough__identity(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def passthrough__identity(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for passthrough__identity — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    return {"out": inputs.get("in")}


__all__ = ["passthrough__identity"]
