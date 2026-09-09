"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.act_safe_boundary_node
stage: control
kind: VALIDATOR
out_port: out
description: Verify the act is within the safe-boundary envelope.

worker: act_safe_boundary_node(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def act_safe_boundary_node(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for act_safe_boundary_node — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    from lca.plugins.lab.control.ops_act import LcaControlActSafeBoundaryProvider
    from agent_lab.primitives.artifact import Artifact
    provider = LcaControlActSafeBoundaryProvider.from_node_config(node.config)
    out_port = node.config.get("to", "allowed")
    result = provider.evaluate(inputs.get("in_args"))
    return {out_port: result.get(out_port, Artifact(kind="fact", content={"allowed": True}))}


__all__ = ["act_safe_boundary_node"]
