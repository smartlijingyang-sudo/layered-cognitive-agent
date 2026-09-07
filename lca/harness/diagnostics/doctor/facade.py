"""Doctor facade orchestrator (ADR-0199 §5.1 / §5.3 / P2-07).

Per ADR-0199 §5.1 Doctor is a compile-pipeline dry-run projection. This
facade composes the four P2 doctor passes into a single
``doctor_profile(path) -> DoctorReport`` call. The CLI (P2-08) and the
web UI (P2-11) consume this facade; per §5.3 the facade is the SINGLE
doctor entry point.

Per I-HPC-7 the facade is read-only on the profile path and plugin
tree: no K3 boot, no journal writes, no network. Resolution failures
are converted to findings or skipped silently.

Pass order (deterministic per C8):
  1. ProfileCompileDryRun   — profile-level compile errors
  2. PluginShapeDoctor      — plugin tree shape violations
  3. CapabilityCardinality  — capability duplicates
  4. PhaseGraphDoctor       — closed-set violations
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
)
from lca.harness.diagnostics.doctor.capability_cardinality import (
    CapabilityCardinalityDoctor,
)
from lca.harness.diagnostics.doctor.compile_dry_run import ProfileCompileDryRun
from lca.harness.diagnostics.doctor.phase_graph import PhaseGraphDoctor
from lca.harness.diagnostics.doctor.plugin_shape import PluginShapeDoctor


class DoctorFacade:
    """Orchestrator that composes the four doctor passes (ADR-0199 P2-07).

    The facade is constructed with optional pass instances; when None,
    default ones are created. This enables:
      - Tests to inject stub passes
      - Future PRs to add additional passes via composition
      - Per-pass configuration without facade-level flags

    Per I-HPC-4 the facade does not mutate any state; it is a pure
    orchestrator. Per I-HPC-7 it makes no network calls, writes no
    journal, and never boots a K3 fiber. Per C8 the pass order is
    deterministic and documented above.
    """

    def __init__(
        self,
        *,
        compile_dry_run: ProfileCompileDryRun | None = None,
        plugin_shape: PluginShapeDoctor | None = None,
        capability_cardinality: CapabilityCardinalityDoctor | None = None,
        phase_graph: PhaseGraphDoctor | None = None,
    ) -> None:
        self._compile_dry_run = compile_dry_run or ProfileCompileDryRun()
        self._plugin_shape = plugin_shape or PluginShapeDoctor()
        self._capability_cardinality = capability_cardinality or CapabilityCardinalityDoctor()
        self._phase_graph = phase_graph or PhaseGraphDoctor()

    def doctor_profile(
        self,
        profile_path: str | Path,
        *,
        include_plugin_shape: bool = True,
        include_capability_cardinality: bool = True,
        include_phase_graph: bool = True,
    ) -> DoctorReport:
        """Run all configured doctor passes and aggregate their findings.

        Per ADR-0199 §5.1 the facade is the SINGLE entry point; the
        order of passes is deterministic and documented above. Each pass
        runs independently; their findings are concatenated and
        re-summarized by DoctorReport.from_findings.

        Per I-HPC-7 the facade never raises for profile-level issues;
        the compile pass converts them to findings and the downstream
        passes are silently skipped when the compile step failed or
        when their required inputs are unavailable.
        """
        profile_path = Path(profile_path)
        findings: list[DoctorFinding] = []
        activation_ref: str | None = None

        # 1. Compile dry-run (always runs; provides activation_ref on
        #    success when the pass propagates it).
        compile_report = self._compile_dry_run.run(profile_path)
        findings.extend(compile_report.findings)
        if compile_report.activation_ref:
            activation_ref = compile_report.activation_ref

        # 2. Plugin shape (opt-in; profile-independent).
        if include_plugin_shape:
            shape_report = self._plugin_shape.run(profile_path)
            findings.extend(shape_report.findings)

        # 3. Capability cardinality — requires the resolved plugin
        #    contracts. If the compile step failed, skip this pass.
        #    If contracts are unavailable, skip silently (I-HPC-7).
        if include_capability_cardinality and not _has_compile_errors(compile_report):
            contracts = self._optional_resolve_contracts(profile_path)
            if contracts is not None:
                cap_report = self._capability_cardinality.run(contracts)
                findings.extend(cap_report.findings)

        # 4. Phase graph — requires the compiled phase graph plan.
        #    If the compile step failed, skip this pass.
        if include_phase_graph and not _has_compile_errors(compile_report):
            phase_plan = self._optional_resolve_phase_graph(profile_path)
            if phase_plan is not None:
                pg_report = self._phase_graph.run(phase_plan)
                findings.extend(pg_report.findings)

        return DoctorReport.from_findings(
            subject=str(profile_path),
            findings=findings,
            activation_ref=activation_ref,
        )

    def _optional_resolve_contracts(self, profile_path: Path) -> list[Any] | None:
        """Resolve plugin contracts if available; return None on failure.

        Per I-HPC-7 failure is silent (None) so the doctor remains
        read-only and does not crash mid-orchestration. The dynamic
        import keeps the facade free of a hard dependency on
        PlanResolutionService at module import time.
        """
        try:
            from lca.application.runtime.plan_resolution import (
                PlanResolutionService,
            )

            service = PlanResolutionService()
            result = service.resolve_refs(profile_path, session_id=None)
            return getattr(result.compiled_plan, "plugin_contracts", None)
        except Exception:
            return None

    def _optional_resolve_phase_graph(self, profile_path: Path) -> Any:
        """Resolve phase graph plan if available; return None on failure."""
        try:
            from lca.application.runtime.plan_resolution import (
                PlanResolutionService,
            )

            service = PlanResolutionService()
            result = service.resolve_refs(profile_path, session_id=None)
            return getattr(result.compiled_plan, "phase_graph_plan", None)
        except Exception:
            return None


def _has_compile_errors(report: DoctorReport) -> bool:
    return report.summary.errors > 0


__all__ = ("DoctorFacade",)
