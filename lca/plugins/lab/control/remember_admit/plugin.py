"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.remember_admit
stage: control
kind: PRODUCER
out_port: out
description: Control-plane wrapper around the remember admit producer.

worker: remember_admit_node(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def remember_admit_node(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for remember_admit_node — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    from lca.plugins.lab.control.ops import LcaControlRememberAdmitProvider
    provider = LcaControlRememberAdmitProvider.from_node_config(node.config)
    out_port = node.config.get("to", "admit_verdict")
    return provider.admit(observation=inputs.get("in_observation"), out_port=out_port)


__all__ = ["remember_admit_node"]
