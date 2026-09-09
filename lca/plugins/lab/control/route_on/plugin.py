"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.route_on
stage: control
kind: ROUTER
out_port: out
description: Route a node output to one of several downstream paths by predicate.

worker: route_on(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def route_on(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for route_on — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    from agent_lab.primitives.artifact import Artifact, ArtifactKind
    key_in = node.config["key_from"]
    table: dict = node.config["table"]
    out_port = node.outs[0]
    key_a = inputs.get(key_in)
    if key_a is None:
        return {out_port: Artifact(kind=ArtifactKind.FACT, content={"routed": None})}
    key = str(key_a.content) if not isinstance(key_a.content, dict) else str(key_a.content.get("verdict", ""))
    chosen_in = table.get(key, node.config.get("default"))
    if chosen_in is None or chosen_in not in inputs:
        return {out_port: Artifact(kind=ArtifactKind.INTENT, content={"tool": "__none__", "args": {}, "verdict": "deny"}, schema_ref="tool.intent.v1")}
    chosen = inputs[chosen_in]
    return {out_port: chosen.model_copy(update={"content": {**chosen.content, "routed_via": key}})}


__all__ = ["route_on"]
