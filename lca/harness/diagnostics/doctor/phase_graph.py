"""Phase graph doctor pass (ADR-0199 §5 / P2-06 + C1).

Per ADR-0199 C1 (认知闭集): the cognitive phase graph is a closed set
of 6 phases (perceive, think, act, reflect, remember, stop). The
PhaseGraphDoctor pass converts each violation into a DOC-PG-NNN finding.

Per I-HPC-7: no K3 boot, no journal writes, no network. Read-only on
the phase graph.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from lca.contracts.diagnostics.doctor import DoctorReport

if TYPE_CHECKING:
    from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
        CognitivePhaseGraphPlan,
    )


# Closed set of 6 cognitive phases (ADR-0199 C1 + ADR-0194 §0).
# Adding a 7th phase requires an ADR; this constant IS the source of truth
# that the doctor enforces.
_CLOSED_PHASES: frozenset[str] = frozenset(
    {
        "perceive",
        "think",
        "act",
        "reflect",
        "remember",
        "stop",
    }
)

_OWNER_ADR: str = "ADR-0199"


class PhaseGraphDoctor:
    """Single doctor pass: phase graph violations → DoctorReport (ADR-0199 P2-06).

    Audits a :class:`CognitivePhaseGraphPlan` against the closed-set
    invariant (C1). Each violation is emitted as a stable
    ``DOC-PG-NNN`` finding; the pass never mutates the plan, never
    reads the filesystem, never boots fibers (I-HPC-7).
    """

    def __init__(self, *, profile_path: str | Path | None = None) -> None:
        self._profile_path = Path(profile_path) if profile_path else None

    def run(self, phase_graph_plan: CognitivePhaseGraphPlan) -> DoctorReport:
        """Audit a phase graph plan against C1 closed-set invariant.

        Per ADR-0194/0199 the six phases are the only legal phase names.
        Each unknown phase is reported as DOC-PG-001 (error).
        Duplicate nodes for the same phase are reported as DOC-PG-002 (error).
        Cycles in the graph are reported as DOC-PG-003 (error).
        """
        from lca.contracts.diagnostics.doctor import DoctorFinding

        subject = str(self._profile_path) if self._profile_path else "phase_graph"
        findings: list[DoctorFinding] = []

        nodes = self._collect_nodes(phase_graph_plan)

        # DOC-PG-001: unknown phases
        for node_name in nodes:
            if node_name not in _CLOSED_PHASES:
                findings.append(
                    DoctorFinding(
                        code="DOC-PG-001",
                        severity="error",
                        owner=_OWNER_ADR,
                        message=(
                            f"phase {node_name!r} is not in the closed set of 6 cognitive "
                            f"phases (ADR-0199 C1)"
                        ),
                        remediation=(
                            f"Use one of: {sorted(_CLOSED_PHASES)}. Adding a 7th phase "
                            f"requires an ADR; see ADR-0199 C1."
                        ),
                        plugin_id=None,
                        plan_ref=None,
                    )
                )

        # DOC-PG-002: duplicate phase nodes (C1 — each phase appears exactly once)
        name_counts: Counter[str] = Counter(nodes)
        for name, count in sorted(name_counts.items()):
            if count > 1:
                findings.append(
                    DoctorFinding(
                        code="DOC-PG-002",
                        severity="error",
                        owner=_OWNER_ADR,
                        message=f"phase {name!r} appears {count} times in the graph",
                        remediation=(
                            "Each phase must appear exactly once in the cognitive loop. "
                            "Verify the phase_graph_plan topology."
                        ),
                        plugin_id=None,
                        plan_ref=None,
                    )
                )

        # DOC-PG-003: cycles
        cycle = self._detect_cycle(nodes)
        if cycle:
            findings.append(
                DoctorFinding(
                    code="DOC-PG-003",
                    severity="error",
                    owner=_OWNER_ADR,
                    message=f"cycle detected in phase graph: {' -> '.join(cycle)}",
                    remediation=(
                        "Use loop_guard_policy to bound cycles (ADR-0194). A phase graph "
                        "without explicit loop guards must be a DAG."
                    ),
                    plugin_id=None,
                    plan_ref=None,
                )
            )

        return DoctorReport.from_findings(subject, findings)

    @staticmethod
    def _collect_nodes(plan: CognitivePhaseGraphPlan) -> list[str]:
        """Extract phase names from the plan's nodes.

        The :class:`CognitivePhaseGraphPlan` owns a ``nodes`` tuple of
        :class:`PhaseNode` records; each record carries a ``semantic_phase``
        whose ``.value`` is the canonical lowercase phase name
        (e.g. ``"perceive"``). This method tolerates alternate shapes
        (e.g. ``phases`` attribute, plain ``str`` nodes) for downstream
        plan refinements while keeping C1 enforcement the SSOT.
        """
        # Primary shape: CognitivePhaseGraphPlan.nodes: tuple[PhaseNode, ...]
        nodes = getattr(plan, "nodes", None)
        if nodes is not None and hasattr(nodes, "__iter__"):
            names: list[str] = []
            for n in nodes:
                # PhaseNode exposes .semantic_phase (SemanticPhase enum)
                # and a string-like .id; prefer the semantic_phase value
                # because that is the closed-set SSOT (C1).
                sp = getattr(n, "semantic_phase", None)
                if sp is not None and hasattr(sp, "value"):
                    names.append(str(sp.value))
                else:
                    names.append(getattr(n, "name", None) or getattr(n, "id", None) or str(n))
            return names

        # Alternate shape: phases: tuple[str, ...] | tuple[PhaseNode, ...]
        phases = getattr(plan, "phases", None)
        if phases is not None and hasattr(phases, "__iter__"):
            return [getattr(p, "name", None) or getattr(p, "value", None) or str(p) for p in phases]

        return []

    @staticmethod
    def _detect_cycle(nodes: list[str]) -> list[str] | None:
        """Detect any repeated name in the sequence; if so return the cycle path.

        This is a SIMPLE cycle detector suitable for small phase graphs.
        For richer graph cycle detection, defer to
        :class:`lca.harness.graph.validation.PhaseGraphValidator`.
        """
        seen: dict[str, int] = {}
        for i, name in enumerate(nodes):
            if name in seen:
                return nodes[seen[name] : i + 1]
            seen[name] = i
        return None


__all__ = ("_CLOSED_PHASES", "PhaseGraphDoctor")
