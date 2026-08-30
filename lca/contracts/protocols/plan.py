"""不可变的 ``CompiledRunPlan`` 数据契约（ADR-0068 / ADR-0075）。

计划的构建、散列、序列化和解释均由 ``lca.harness.plan`` 拥有；本模块只定义
跨层交换的稳定数据形状。运行期不得修改计划，任何变更都必须重新编译为新的
plan reference。

控制面只以原生 ``PluginSpec.contributes`` 投影出的 ``control_entries`` 表示。
旧 ``ControlPlan`` 不再进入运行计划，避免同一控制决策同时拥有两套事实源。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.protocols.capability_plan import CapabilityPlan
from lca.contracts.protocols.declarative_common import DECLARATIVE_PLAN_VERSION
from lca.contracts.protocols.declarative_graph import (
    ActionAuthorityPlan,
    CapabilityBinding,
    CognitivePhaseGraphPlan,
    EffectPolicyPlan,
    PhaseBinding,
    PlanProvenance,
    ReplacementDecision,
    ValidationReport,
)
from lca.contracts.protocols.declarative_graph import (
    ControlEntry as DeclarativeControlEntry,
)
from lca.contracts.protocols.declarative_plugin import PluginSpec
from lca.contracts.protocols.scope_plan import ScopePlan

# Schema version for CompiledRunPlan. v2 evolves v1; it is not a parallel plan.
COMPILED_RUN_PLAN_VERSION: str = DECLARATIVE_PLAN_VERSION


@dataclass(frozen=True, slots=True)
class CompiledRunPlan:
    """The immutable plan data consumed by the runtime.

    ``capability`` and ``scope`` retain the ADR-0068 data regions.  The
    ADR-0075 declarations, including the sole executable control projection,
    travel with them as one immutable value. ``phase_graph`` is ``None`` only
    for direct-construction tests; production ``compile_plan`` supplies the
    complete declarative region.
    """

    profile_path: str
    capability: CapabilityPlan
    scope: ScopePlan
    plan_version: str = COMPILED_RUN_PLAN_VERSION
    input_provenance: tuple[tuple[str, str], ...] = ()
    revision: str = "v2"
    plugin_specs: tuple[PluginSpec, ...] = ()
    capability_bindings: tuple[CapabilityBinding, ...] = ()
    phase_graph: CognitivePhaseGraphPlan | None = None
    phase_bindings: tuple[PhaseBinding, ...] = ()
    control_entries: tuple[DeclarativeControlEntry, ...] = ()
    replacement_map: tuple[ReplacementDecision, ...] = ()
    effect_policy: EffectPolicyPlan | None = None
    action_authority: ActionAuthorityPlan | None = None
    provenance: PlanProvenance | None = None
    validation_report: ValidationReport = field(default_factory=ValidationReport)

    def __post_init__(self) -> None:
        if not self.profile_path:
            raise ValueError("CompiledRunPlan.profile_path must be non-empty")
        if not isinstance(self.input_provenance, tuple):
            object.__setattr__(self, "input_provenance", tuple(self.input_provenance))
        normalized: list[tuple[str, str]] = []
        for item in self.input_provenance:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError(f"input_provenance item must be (kind, path) tuple, got {item!r}")
            kind, path = item
            normalized.append((str(kind), str(path)))
        object.__setattr__(self, "input_provenance", tuple(normalized))
        for name in (
            "plugin_specs",
            "capability_bindings",
            "phase_bindings",
            "control_entries",
            "replacement_map",
        ):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                object.__setattr__(self, name, tuple(value))


__all__ = ["COMPILED_RUN_PLAN_VERSION", "CompiledRunPlan"]
