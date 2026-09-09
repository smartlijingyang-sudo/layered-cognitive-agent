"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.observe_checkpoint
stage: control
kind: TRANSFORMER
out_port: out
description: Observe node_start / node_end events for checkpointing.

worker: observe_checkpoint_node(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def observe_checkpoint_node(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for observe_checkpoint_node — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    from lca.plugins.lab.control.ops import LcaControlCheckpointProvider
    provider = LcaControlCheckpointProvider.from_node_config(node.config)
    out_port = node.config.get("to", "checkpoint_event")
    event_type = node.config.get("event_type", "checkpoint")
    return provider.emit(event_type=event_type, event_log=inputs.get("in_event_log"), out_port=out_port)


__all__ = ["observe_checkpoint_node"]
