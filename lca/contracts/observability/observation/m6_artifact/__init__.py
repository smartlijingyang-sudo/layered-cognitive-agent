"""M6 — Artifact snapshot (节点退出时的完整 artifacts 状态).

Producer:  observation.artifact_snapshot (query-time 聚合)
Consumers: lca-ops trace show, diagnosis.failure_explainer
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ArtifactSnapshot(BaseModel):
    """节点退出时的完整 artifacts dict 快照。

    artifacts 字段保留 decision / observation / reflection / degradation
    全部内容(per phase_governance._contribution_context 的 schema)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    node_id: str
    phase: str
    artifacts: dict[str, Any]
    context_digest: str | None = None
    snapshotted_at: str


__all__ = ["ArtifactSnapshot"]
