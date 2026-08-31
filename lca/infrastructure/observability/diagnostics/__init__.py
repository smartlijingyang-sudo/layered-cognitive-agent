"""observability.diagnostics — diagnostic patterns."""

from lca.infrastructure.observability.diagnostics.diagnostic_emitters import (
    record_llm_completion,
    record_memory_operation,
)
from lca.infrastructure.observability.diagnostics.diagnostics import (
    DiagnosePattern,
    DiagnosisReport,
    Finding,
    diagnose,
    diagnose_approval_rejected,
    diagnose_loop_stuck,
    diagnose_memory_poisoned,
    diagnose_model_not_seen,
)

__all__ = [
    "DiagnosePattern",
    "DiagnosisReport",
    "Finding",
    "diagnose",
    "diagnose_approval_rejected",
    "diagnose_loop_stuck",
    "diagnose_memory_poisoned",
    "diagnose_model_not_seen",
    "record_llm_completion",
    "record_memory_operation",
]
