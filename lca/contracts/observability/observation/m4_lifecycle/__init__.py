"""M4 — Lifecycle (装配期事件:plan 编译 / sub_spec_ref resolve / bundle load).

Producers: observation.lifecycle.plan_compile, observation.lifecycle.subgraph_resolve,
          observation.lifecycle.bundle_load
Consumers: diagnosis.blueprint_trajectory_differ, lca-ops run explain
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PlanCompileComplete(BaseModel):
    """plan 编译成功。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    plan_ref: str
    profile_path: str
    compiled_at: str


class PlanCompileFailed(BaseModel):
    """plan 编译失败。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    profile_path: str
    exception_class: str
    exception_message: str
    traceback_text: str
    failed_at: str


class SubgraphResolve(BaseModel):
    """sub_spec_ref 解析结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    plan_ref: str
    owner_node_id: str  # 持有 sub_spec_ref 的 outer 节点
    entry_node: str
    status: str  # resolved / failed
    sub_blueprint_digest: str | None = None
    failure_reason: str | None = None
    resolved_at: str


class BundleLoad(BaseModel):
    """bundle / plugin 装载结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    bundle_id: str
    plugin_id: str | None = None
    status: str  # loaded / missing / failed
    version: str | None = None
    failure_reason: str | None = None
    loaded_at: str


__all__ = [
    "BundleLoad",
    "PlanCompileComplete",
    "PlanCompileFailed",
    "SubgraphResolve",
]
