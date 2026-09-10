"""M3 — Node exit (节点退出时的现场).

Producer:  observation.node_trajectory (end 部分)
Consumers: diagnosis.blueprint_trajectory_differ, lca-ops trace show --node <id>
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class NodeException(BaseModel):
    """节点退出时抛出的异常:类型 + 消息 + traceback(完整)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exception_class: str
    exception_message: str
    traceback_text: str
    source_location: str | None = None


class NodeExit(BaseModel):
    """节点退出时的完整现场:outputs payload + exit status + exception。

    outputs 是节点 executor 返回的完整对象(decision / control_verdict /
    tool_result / reflection 等),不 digest 不摘要 —— agent 看到的是
    节点产出的真实对象,而不是 hash。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    node_id: str
    phase: str
    binding: str | None = None
    parent_node_id: str | None = None
    sub_graph_id: str | None = None
    exit_status: str  # success / error / skipped
    elapsed_ms: int = 0
    outputs: dict[str, Any] = {}
    exception: NodeException | None = None
    exited_at: str


__all__ = ["NodeException", "NodeExit"]
