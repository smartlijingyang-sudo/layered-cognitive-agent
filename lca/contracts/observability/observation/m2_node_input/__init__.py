"""M2 — Node entry (节点进入时的现场).

Producer:  observation.node_trajectory (start 部分)
Consumers: diagnosis.blueprint_trajectory_differ, lca-ops trace show --node <id>
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.harness.tasks.session import session_event


@session_event("observation.node_enter", visibility="audit")
class NodeEnter(BaseModel):
    """节点进入时的完整现场:identity + input payload + time。

    inputs 是节点 executor 接收的完整对象,不 digest 不摘要 ——
    agent 看到的是节点拿到的真实输入,而不是 hash。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    node_id: str
    # LCA lifecycle phase owning the node (``perceive`` / ``think`` /
    # ``act`` / ``reflect`` / ``remember`` / ``stop``). Derived from
    # node_id by the kernel; empty string means "phase unknown" (e.g.
    # ad-hoc test plans that bypass the canonical naming convention).
    phase: str = ""
    binding: str | None = None
    parent_node_id: str | None = None
    sub_graph_id: str | None = None
    depth: int = 0
    visit_count: int = 1
    entered_at: str
    inputs: dict[str, Any]


__all__ = ["NodeEnter"]
