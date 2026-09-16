"""Run-health typed contracts (PR-1 / Task 1.1 + Task 1.2).

The DTOs and the ``HealthDeriver`` Protocol in this package form the
cross-boundary health contract for every observability consumer (SOP,
debug, manifest, agent CLI). All DTOs uphold AGENTS.md §3 C13
(information bloodline closure): ``frozen=True, extra="forbid"``; see
each module's docstring for the specific obligation it carries.

The ``HealthDeriver`` Protocol upholds AGENTS.md §3 C13 (D1 definition
surface) and §5 (change closure): adding a new health dimension is one
new file + one ``pyproject.toml`` line. The fold function in
``lca/plugins/observability/health/`` discovers derivers via
``importlib.metadata.entry_points(group="lca.health_derivers")``.

Re-exports:
    ``EvidenceRef`` — typed pointer to a specific spine event.
    ``RunHealthCondition`` — one observable fact about a run.
    ``RunHealthStatus`` — the closed 4-value status alphabet.
    ``RunHealthSummary`` — counters + per-type status map.
    ``RunHealthReport`` — top-level frozen report; hashable + comparable.
    ``HealthDeriver`` — structural Protocol for pluggable derivers.
"""

from lca.contracts.observability.health.condition import (
    RunHealthCondition as RunHealthCondition,
)
from lca.contracts.observability.health.condition import (
    RunHealthStatus as RunHealthStatus,
)
from lca.contracts.observability.health.deriver import (
    HealthDeriver as HealthDeriver,
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
    "HealthDeriver",
    "RunHealthCondition",
    "RunHealthReport",
    "RunHealthStatus",
    "RunHealthSummary",
]
