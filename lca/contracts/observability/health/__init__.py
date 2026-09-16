"""Run-health typed contracts (PR-1 / Task 1.1).

The four DTOs in this package form the cross-boundary health contract for
every observability consumer (SOP, debug, manifest, agent CLI). All four
uphold AGENTS.md §3 C13 (information bloodline closure):
``frozen=True, extra="forbid"``; see each module's docstring for the
specific obligation it carries.

Re-exports:
    ``EvidenceRef`` — typed pointer to a specific spine event.
    ``RunHealthCondition`` — one observable fact about a run.
    ``RunHealthStatus`` — the closed 4-value status alphabet.
    ``RunHealthSummary`` — counters + per-type status map.
    ``RunHealthReport`` — top-level frozen report; hashable + comparable.
"""

from lca.contracts.observability.health.condition import (
    RunHealthCondition as RunHealthCondition,
)
from lca.contracts.observability.health.condition import (
    RunHealthStatus as RunHealthStatus,
)
from lca.contracts.observability.health.evidence_ref import (
    EvidenceRef as EvidenceRef,
)
from lca.contracts.observability.health.report import (
    RunHealthReport as RunHealthReport,
)
from lca.contracts.observability.health.report import (
    RunHealthSummary as RunHealthSummary,
)

__all__ = [
    "EvidenceRef",
    "RunHealthCondition",
    "RunHealthReport",
    "RunHealthStatus",
    "RunHealthSummary",
]
