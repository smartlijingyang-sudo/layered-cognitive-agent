"""Observation contracts —— 9 modules,每个子问题一个 module。

子问题 → module 映射(第一性原理):
  M1 期望        → PlanBlueprint
  M2 输入现场    → NodeEnter
  M3 输出现场    → NodeExit
  M4 装配期      → PlanCompileComplete / PlanCompileFailed / SubgraphResolve / BundleLoad
  M5 事件轨迹    → DecisionTrace / ControlTrace / ToolCallTrace / LLMCallTrace / ReducerApply
  M6 artifact    → ArtifactSnapshot
  M7 偏差        → DiffReport
  M8 根因        → FailureExplanation
  M9 回放        → RunReplay

所有 schema 走 Pydantic frozen + extra="forbid"(AGENTS.md C13)。
所有 fact 走 Session.append 单轨(ADR-0186/0191/0194)。
"""

from __future__ import annotations

from lca.contracts.observability.observation.m1_blueprint import (
    PlanBlueprint as PlanBlueprint,
)
from lca.contracts.observability.observation.m1_blueprint import (
    PlanEdgeSpec as PlanEdgeSpec,
)
from lca.contracts.observability.observation.m1_blueprint import (
    PlanNodeSpec as PlanNodeSpec,
)
from lca.contracts.observability.observation.m2_node_input import (
    NodeEnter as NodeEnter,
)
from lca.contracts.observability.observation.m3_node_output import (
    NodeException as NodeException,
)
from lca.contracts.observability.observation.m3_node_output import (
    NodeExit as NodeExit,
)
from lca.contracts.observability.observation.m4_lifecycle import (
    BundleLoad as BundleLoad,
)
from lca.contracts.observability.observation.m4_lifecycle import (
    PlanCompileComplete as PlanCompileComplete,
)
from lca.contracts.observability.observation.m4_lifecycle import (
    PlanCompileFailed as PlanCompileFailed,
)
from lca.contracts.observability.observation.m4_lifecycle import (
    SubgraphResolve as SubgraphResolve,
)
from lca.contracts.observability.observation.m5_event_traces import (
    ControlTrace as ControlTrace,
)
from lca.contracts.observability.observation.m5_event_traces import (
    DecisionTrace as DecisionTrace,
)
from lca.contracts.observability.observation.m5_event_traces import (
    LLMCallTrace as LLMCallTrace,
)
from lca.contracts.observability.observation.m5_event_traces import (
    ReducerApply as ReducerApply,
)
from lca.contracts.observability.observation.m5_event_traces import (
    ToolCallTrace as ToolCallTrace,
)
from lca.contracts.observability.observation.m6_artifact import (
    ArtifactSnapshot as ArtifactSnapshot,
)
from lca.contracts.observability.observation.m7_diff import (
    ContractViolation as ContractViolation,
)
from lca.contracts.observability.observation.m7_diff import (
    DiffReport as DiffReport,
)
from lca.contracts.observability.observation.m7_diff import (
    EdgeDeviation as EdgeDeviation,
)
from lca.contracts.observability.observation.m7_diff import (
    MissingNode as MissingNode,
)
from lca.contracts.observability.observation.m7_diff import (
    UnexpectedNode as UnexpectedNode,
)
from lca.contracts.observability.observation.m8_explanation import (
    FailureExplanation as FailureExplanation,
)
from lca.contracts.observability.observation.m8_explanation import (
    RemediationHint as RemediationHint,
)
from lca.contracts.observability.observation.m8_explanation import (
    RootCauseStep as RootCauseStep,
)
from lca.contracts.observability.observation.m9_replay import (
    ReplayDiffSummary as ReplayDiffSummary,
)
from lca.contracts.observability.observation.m9_replay import (
    ReplayStep as ReplayStep,
)
from lca.contracts.observability.observation.m9_replay import (
    RunReplay as RunReplay,
)

__all__ = [
    "ArtifactSnapshot",
    "BundleLoad",
    "ContractViolation",
    "ControlTrace",
    "DecisionTrace",
    "DiffReport",
    "EdgeDeviation",
    "FailureExplanation",
    "LLMCallTrace",
    "MissingNode",
    "NodeEnter",
    "NodeException",
    "NodeExit",
    "PlanBlueprint",
    "PlanCompileComplete",
    "PlanCompileFailed",
    "PlanEdgeSpec",
    "PlanNodeSpec",
    "ReducerApply",
    "RemediationHint",
    "ReplayDiffSummary",
    "ReplayStep",
    "RootCauseStep",
    "RunReplay",
    "SubgraphResolve",
    "ToolCallTrace",
    "UnexpectedNode",
]
