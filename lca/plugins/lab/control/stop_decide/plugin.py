"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.stop_decide
stage: control
kind: VALIDATOR
out_port: out
description: Decide if the loop should stop after a phase.

worker: stop_decide(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def stop_decide(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for stop_decide — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    from lca.plugins.lab.control.ops import LcaControlStopPolicyProvider
    provider = LcaControlStopPolicyProvider.from_node_config(node.config)
    out_port = node.config.get("to", "stop_decision")
    return provider.decide(
        state=inputs.get("in_state"),
        decision=inputs.get("in_decision"),
        observation=inputs.get("in_observation"),
        reflection=inputs.get("in_reflection"),
        out_port=out_port,
    )


__all__ = ["stop_decide"]
