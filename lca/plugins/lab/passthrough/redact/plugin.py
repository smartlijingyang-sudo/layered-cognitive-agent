"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.passthrough.redact
stage: passthrough
kind: PASSTHROUGH
out_port: out
description: Apply redaction patterns.

worker: redact(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def redact(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for redact — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    src = node.config.get("from", node.ins[0])
    dst = node.config.get("to", node.outs[0])
    patterns = list(node.config.get("patterns", []) or [])
    src_a = inputs.get(src)
    if src_a is None:
        return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
    text = str(src_a.content)
    for pat in patterns:
        text = text.replace(pat, "[REDACTED]")
    return {dst: Artifact(kind=ArtifactKind.TEXT, content=text, schema_ref="redacted.v1")}


__all__ = ["redact"]
