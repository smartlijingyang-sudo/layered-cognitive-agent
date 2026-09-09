"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.act_authorize_node
stage: control
kind: VALIDATOR
out_port: out
description: Control-plane wrapper around the act authorize node.

worker: act_authorize_node(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def act_authorize_node(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for act_authorize_node — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    from lca.plugins.lab.control.ops_act import LcaControlActAuthorizeProvider
    from agent_lab.primitives.artifact import Artifact
    provider = LcaControlActAuthorizeProvider.from_node_config(node.config)
    out_port = node.config.get("to", "allowed")
    result = provider.evaluate(inputs.get("in_args"))
    return {out_port: result.get(out_port, Artifact(kind="fact", content={"allowed": True}))}


__all__ = ["act_authorize_node"]
