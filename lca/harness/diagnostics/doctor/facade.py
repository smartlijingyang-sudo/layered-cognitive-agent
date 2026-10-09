"""Doctor facade orchestrator (ADR-0199 §5.1 / §5.3 / P2-07).

Per ADR-0199 §5.1 Doctor is a compile-pipeline dry-run projection. This
facade composes the doctor passes that have real production inputs into a
single ``doctor_profile(path) -> DoctorReport`` call. The CLI (P2-08) and the
web UI (P2-11) consume this facade; per §5.3 the facade is the SINGLE
doctor entry point.

Per I-HPC-7 the facade is read-only on the profile path and plugin
tree: no K3 boot, no journal writes, no network. Resolution failures
are converted to findings.

Passes wired (RA-051): only these two have real production inputs —
  1. ProfileCompileDryRun   — profile-level compile errors
  2. PluginShapeDoctor      — plugin tree shape violations

NOT wired (RA-051): CapabilityCardinality, PhaseGraphDoctor,
PrivilegeDoctor, TrustDoctor. Their required inputs (``plugin_contracts``
/ ``phase_graph_plan`` projections) do not exist on the compiled plan
seam: ``CompiledRunPlan`` is a slots dataclass with neither attribute,
and ``V2ExecutablePlan`` delegates unknown attributes to ``inner`` which
lacks them too, so any ``getattr`` lookup always returned None and the
passes silently skipped in production per I-HPC-7. The read-only rule
forbids the facade from materializing those inputs itself, so the wiring
was dead orchestration and was deleted rather than left to silently
skip. The four modules remain importable as library passes for callers
that can supply their inputs directly; they keep their own test modules.

Not wired (RA-039): ResourceDoctor. It needs a live ResourceRegistry plus
the harness provider names to audit orphans against, and neither exists
at doctor time (doctor is read-only on the profile path + plugin tree;
no K3 boot per I-HPC-7). Wiring it with an empty provider set would emit
false-positive DOC-RES-* orphans on every run. When a registry source
exists, wire it here with an include_resource switch in the same style.
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
)
from lca.harness.diagnostics.doctor.compile_dry_run import ProfileCompileDryRun
from lca.harness.diagnostics.doctor.plugin_shape import PluginShapeDoctor


class DoctorFacade:
    """Orchestrator that composes the two wired doctor passes (ADR-0199 P2-07, RA-039, RA-051).

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
    ) -> None:
        self._compile_dry_run = compile_dry_run or ProfileCompileDryRun()
        self._plugin_shape = plugin_shape or PluginShapeDoctor()

    def doctor_profile(
        self,
        profile_path: str | Path,
        *,
        include_plugin_shape: bool = True,
    ) -> DoctorReport:
        """Run all configured doctor passes and aggregate their findings.

        Per ADR-0199 §5.1 the facade is the SINGLE entry point; the
        order of passes is deterministic and documented above. Each pass
        runs independently; their findings are concatenated and
        re-summarized by DoctorReport.from_findings.

        Per I-HPC-7 the facade never raises for profile-level issues;
        the compile pass converts them to findings.
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

        return DoctorReport.from_findings(
            subject=str(profile_path),
            findings=findings,
            activation_ref=activation_ref,
        )


__all__ = ("DoctorFacade",)
