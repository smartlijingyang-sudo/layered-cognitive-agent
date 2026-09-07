"""Profile compile dry-run — single Doctor pass (ADR-0199 P2-03).

Per ADR-0199 §5.1 doctor is a compile-pipeline projection. This pass
runs K1 (resolve_profile) + K2 (compile_plan) WITHOUT booting a cordis
Context, and converts every caught exception into a stable DoctorFinding.

Per I-HPC-7:
  - NO journal writes
  - NO K3 boot / fiber spawn
  - NO network I/O
  - NO subprocess calls
  - Read-only on the profile path; results are surfaced via DoctorReport.

Per C8: output is deterministic — same profile_path + same inputs → same
findings. session_id is NOT used here (doctor is pre-activation).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
)
from lca.harness.composition.plan_compiler import PlanCompilerError, compile_plan
from lca.harness.plan import compiled_run_plan_ref
from lca.harness.profile.resolve.resolve import resolve_profile

if TYPE_CHECKING:
    from lca.application.runtime.plan_resolution import PlanResolutionService


# Owner ADR for code attribution in findings.
_OWNER_ADR: str = "ADR-0199"


class DoctorCompileError(RuntimeError):
    """Raised only when the Doctor itself fails (NOT a profile bug).

    Profile-level failures (resolve/compile errors) are surfaced as
    DoctorFinding, not exceptions. This exception is for cases like
    invalid profile_path type or doctor-internal invariant violations.
    """


class ProfileCompileDryRun:
    """Single Doctor pass: resolve_profile + compile_plan → DoctorReport.

    Per ADR-0199 §5.2 every finding has a stable machine code so that
    suppression rules and CI baselines are robust to message wording.
    This pass emits DOC-COMPAT-* codes for compile-level failures and
    leaves DOC-PS-* / DOC-CAP-* / DOC-PG-* codes for other passes
    (P2-04 / P2-05 / P2-06).
    """

    def __init__(
        self,
        plan_resolution_service: PlanResolutionService | None = None,
    ) -> None:
        # Optional injection — when None, the pass uses the lower-level
        # resolve_profile + compile_plan directly. When provided, the
        # richer PlanResolutionService is used (gives consistent error
        # wrapping with the runtime facade).
        self._service = plan_resolution_service

    def run(self, profile_path: str | Path) -> DoctorReport:
        """Run the compile dry-run for a single profile path.

        Returns a DoctorReport (never raises for profile-level failures).
        Raises DoctorCompileError only for invalid inputs (e.g., None
        or empty string).
        """
        if profile_path is None or profile_path == "":
            raise DoctorCompileError("profile_path must be non-empty")

        path = Path(profile_path)
        subject = str(path)
        findings: list[DoctorFinding] = []

        # 1. Try resolve + compile
        try:
            if self._service is not None:
                # When a PlanResolutionService is injected, defer to it
                # for richer error wrapping. session_id is None because
                # doctor runs pre-activation (C8 determinism).
                result = self._service.resolve_refs(path, session_id=None)
                plan_ref = result.plan_ref
            else:
                resolved = resolve_profile(path)
                compiled = compile_plan(resolved)
                # compiled_run_plan_ref is the deterministic SSOT for the
                # compiled plan's hash; per ADR-0199 §5.2 the doctor
                # surfaces this as the success marker's plan_ref.
                plan_ref = compiled_run_plan_ref(compiled)
        except PlanCompilerError as exc:
            findings.append(
                DoctorFinding(
                    code="DOC-COMPAT-001",
                    severity="error",
                    owner=_OWNER_ADR,
                    message=f"plan compile failed: {exc}",
                    remediation=(
                        "Run `./scripts/lca-ops plan compile <profile>` for the "
                        "underlying error and consult ADR-0199 §5.1."
                    ),
                    plugin_id=None,
                    plan_ref=None,
                )
            )
            return DoctorReport.from_findings(subject, findings)
        except FileNotFoundError as exc:
            findings.append(
                DoctorFinding(
                    code="DOC-COMPAT-002",
                    severity="error",
                    owner=_OWNER_ADR,
                    message=f"profile not found: {exc.filename or path}",
                    remediation=(f"Verify the profile path '{subject}' exists and is readable."),
                    plugin_id=None,
                    plan_ref=None,
                )
            )
            return DoctorReport.from_findings(subject, findings)
        except (ValueError, TypeError) as exc:
            # ProfileResolveError extends ValueError so this handler also
            # catches resolve-time failures (invalid YAML, duplicate ids,
            # layer violations, missing capabilities, ...).
            findings.append(
                DoctorFinding(
                    code="DOC-COMPAT-003",
                    severity="error",
                    owner=_OWNER_ADR,
                    message=f"profile invalid: {exc}",
                    remediation=(
                        "Inspect the profile YAML; common causes: missing required "
                        "fields, invalid plugin ids, undeclared capabilities."
                    ),
                    plugin_id=None,
                    plan_ref=None,
                )
            )
            return DoctorReport.from_findings(subject, findings)

        # 2. Compile succeeded — surface an info finding with the plan_ref.
        # Per ADR-0199 §5.2 plan_ref is populated on successful compile.
        # DoctorFinding.__post_init__ enforces non-empty remediation, so the
        # success marker carries a short hint instead of an empty string.
        findings.append(
            DoctorFinding(
                code="DOC-COMPAT-000",
                severity="info",
                owner=_OWNER_ADR,
                message=f"compile OK: plan_ref={plan_ref}",
                remediation="no action — profile compiles cleanly",
                plugin_id=None,
                plan_ref=plan_ref,
            )
        )
        return DoctorReport.from_findings(subject, findings)


__all__ = ("DoctorCompileError", "ProfileCompileDryRun")
