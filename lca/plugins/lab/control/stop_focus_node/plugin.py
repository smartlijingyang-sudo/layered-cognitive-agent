"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.stop_focus_node
stage: control
kind: VALIDATOR
out_port: out
description: Stop the loop on focused evaluation criteria.

worker: stop_focus(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def stop_focus(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for stop_focus — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    from lca.plugins.lab.control.ops import LcaControlStopFocusProvider
    provider = LcaControlStopFocusProvider.from_node_config(node.config)
    out_port = node.config.get("to", "focus_verdict")
    return provider.evaluate(
        state=inputs.get("in_state"),
        decision=inputs.get("in_decision"),
        out_port=out_port,
    )


__all__ = ["stop_focus"]
