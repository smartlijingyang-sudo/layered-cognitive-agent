"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.passthrough.rank_v2
stage: passthrough
kind: PASSTHROUGH
out_port: out
description: Rank v2.

worker: passthrough__rank(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def passthrough__rank(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for passthrough__rank — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    text_a = inputs.get("text")
    text = text_a.content if text_a else ""
    sep = node.config.get("split_on", "\n")
    keep = int(node.config.get("keep", 50))
    lines = text.split(sep) if text else []
    joined = sep.join(lines[:keep])
    if text_a is None:
        return {"out": Artifact(kind=ArtifactKind.TEXT, content="")}
    return {"out": Artifact(kind=text_a.kind, content=joined, schema_ref=text_a.schema_ref)}


__all__ = ["passthrough__rank"]
