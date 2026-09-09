"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.passthrough.redact_v2
stage: passthrough
kind: PASSTHROUGH
out_port: out
description: Redact v2.

worker: passthrough__redact(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def passthrough__redact(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for passthrough__redact — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    text_a = inputs.get("text")
    text = text_a.content if text_a else ""
    for pat in node.config.get("patterns", []) or []:
        text = text.replace(pat, "[REDACTED]")
    if text_a is None:
        return {"out": Artifact(kind=ArtifactKind.TEXT, content="")}
    return {"out": Artifact(kind=text_a.kind, content=text, schema_ref=text_a.schema_ref)}


__all__ = ["passthrough__redact"]
