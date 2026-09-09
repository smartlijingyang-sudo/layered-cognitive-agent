"""Auto-reflected typed worker — replaces _XxxWorker.execute.

id: lab.control.think_guard
stage: control
kind: VALIDATOR
out_port: out
description: Control-plane wrapper around the think guard validator.

worker: think_guard_node(*, inputs, from_port, to_port) -> dict[str, Artifact]
config: from_port to_port
"""
from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def think_guard_node(
    *,
    inputs: dict[str, Artifact],
    from_port: str = "in",
    to_port: str = "out",
    **config: Any,
) -> dict[str, Artifact]:
    """Typed wrapper for think_guard_node — 原 execute 体 inline。"""
    config = dict(config)
    # 原 execute body 内的局部变量:
    node = None  # 已迁移到 config / inputs
    seams = None

    from lca.plugins.lab.control.think_guard.ops import handle_control_decision
    cfg = node.config or {}
    provider_cfg = dict(cfg.get("provider_config") or {})
    mode = str(provider_cfg.get("mode") or cfg.get("mode") or "passthrough")
    out_port = cfg.get("to", "out_decision")
    enforce_cfg = {k: v for k, v in provider_cfg.items() if k != "mode"}
    return handle_control_decision(inputs.get("in_decision"), mode=mode, out_port=out_port, enforce_config=enforce_cfg)


__all__ = ["think_guard_node"]
