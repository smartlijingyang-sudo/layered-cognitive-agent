# COMPAT(owner: ADR-0194, from: lca.harness.declarative.compile.phase_governance,
# to: lca.harness.graph.governance.phase_governance,
# delete_when: rg "from lca\\.harness\\.declarative\\.compile\\.phase_governance" 生产引用归零,
# forbidden_new_usage: 新代码优先 from lca.harness.graph.governance import ...)
"""COMPAT re-export — see ``lca.harness.graph.governance``."""

from lca.harness.graph.governance.phase_governance import (
    ControlVerdictInterpretation,
    GovernanceResult,
    PhaseGovernance,
    classify_control_verdict,
    control_stop_decision,
    interpret_control_verdict,
)

__all__ = [
    "ControlVerdictInterpretation",
    "GovernanceResult",
    "PhaseGovernance",
    "classify_control_verdict",
    "control_stop_decision",
    "interpret_control_verdict",
]
