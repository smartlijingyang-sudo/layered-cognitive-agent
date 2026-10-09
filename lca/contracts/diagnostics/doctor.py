"""Plugin Doctor contracts (ADR-0199 §5).

Doctor is a compile-pipeline dry-run projection — see ADR-0199 §5.1.
It produces a stable, machine-readable report so that `lca-ops doctor
profile <path> --ci --json` can fail-closed in CI without re-implementing
validation logic.

Invariants:
  I-HPC-7 (Doctor 只读) — no I/O, no K3 boot, no journal writes.
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass
from typing import Any, Literal

DoctorSeverity = Literal["error", "warning", "info"]

# Stable machine code prefix; full code follows the convention DOC-<DOMAIN>-<NNN>.
# Domain examples: PS (plugin shape), CAP (capability), PG (phase graph),
# PRIV (privilege), RES (resource), TRUST (trust), COMPAT (compat).
DoctorDomain = Literal["PS", "CAP", "PG", "PRIV", "RES", "TRUST", "COMPAT"]

# Stable code regex enforced at construction time:
#   ^DOC-[A-Z]{2,6}-\d{3,}$
_DOCTOR_CODE_PATTERN = _re.compile(r"^DOC-[A-Z]{2,6}-\d{3,}$")


@dataclass(frozen=True, slots=True)
class DoctorFinding:
    """A single diagnostic finding from the compile-pipeline dry-run.

    Per ADR-0199 §5.2: every finding has a stable machine code so that
    suppression rules and CI baselines are robust to message wording.
    """

    code: str  # DOC-XX-NNN
    severity: DoctorSeverity
    owner: str  # ADR number (e.g. ADR-0199) or script owner
    message: str  # human-readable description
    remediation: str  # human-readable fix hint
    plugin_id: str | None = None  # None for profile-level findings
    plan_ref: str | None = None  # populated when compile succeeded

    def __post_init__(self) -> None:
        if not _DOCTOR_CODE_PATTERN.match(self.code):
            raise ValueError(f"Doctor code must match DOC-<DOMAIN>-<NNN>; got {self.code!r}")
        if self.severity not in ("error", "warning", "info"):
            raise ValueError(f"severity must be error/warning/info; got {self.severity!r}")
        if not self.message:
            raise ValueError("message must be non-empty")
        if not self.remediation:
            raise ValueError("remediation must be non-empty")


@dataclass(frozen=True, slots=True)
class DoctorSummary:
    """Aggregate counts derived from a DoctorReport's findings."""

    total: int
    errors: int
    warnings: int
    info: int

    def __post_init__(self) -> None:
        if self.total < 0:
            raise ValueError("total must be >= 0")
        if self.errors < 0 or self.warnings < 0 or self.info < 0:
            raise ValueError("counts must be >= 0")
        if self.errors + self.warnings + self.info != self.total:
            raise ValueError(
                f"summary counts inconsistent: errors({self.errors}) + "
                f"warnings({self.warnings}) + info({self.info}) != total({self.total})"
            )


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Aggregate diagnostic report (ADR-0199 §5.2)."""

    subject: str  # profile path or plugin path
    findings: tuple[DoctorFinding, ...]
    summary: DoctorSummary
    activation_ref: str | None = None  # set when compile succeeded

    def __post_init__(self) -> None:
        if not self.subject:
            raise ValueError("subject must be non-empty")
        # Summary must reflect actual findings.
        actual_errors = sum(1 for f in self.findings if f.severity == "error")
        actual_warnings = sum(1 for f in self.findings if f.severity == "warning")
        actual_info = sum(1 for f in self.findings if f.severity == "info")
        actual_total = len(self.findings)
        expected = (
            self.summary.total,
            self.summary.errors,
            self.summary.warnings,
            self.summary.info,
        )
        actual = (actual_total, actual_errors, actual_warnings, actual_info)
        if actual != expected:
            raise ValueError(f"summary mismatch: findings say {actual}, summary says {expected}")

    @classmethod
    def from_findings(
        cls,
        subject: str,
        findings: list[DoctorFinding] | tuple[DoctorFinding, ...],
        *,
        activation_ref: str | None = None,
    ) -> DoctorReport:
        """Build a DoctorReport from a list of findings; auto-computes summary."""
        findings_tuple = tuple(findings)
        errors = sum(1 for f in findings_tuple if f.severity == "error")
        warnings = sum(1 for f in findings_tuple if f.severity == "warning")
        info = sum(1 for f in findings_tuple if f.severity == "info")
        return cls(
            subject=subject,
            findings=findings_tuple,
            summary=DoctorSummary(
                total=len(findings_tuple),
                errors=errors,
                warnings=warnings,
                info=info,
            ),
            activation_ref=activation_ref,
        )

    def to_jsonable(self) -> dict[str, Any]:
        """Stable JSON projection for `--ci --json` output."""
        return {
            "subject": self.subject,
            "activation_ref": self.activation_ref,
            "summary": {
                "total": self.summary.total,
                "errors": self.summary.errors,
                "warnings": self.summary.warnings,
                "info": self.summary.info,
            },
            "findings": [
                {
                    "code": f.code,
                    "severity": f.severity,
                    "owner": f.owner,
                    "message": f.message,
                    "remediation": f.remediation,
                    "plugin_id": f.plugin_id,
                    "plan_ref": f.plan_ref,
                }
                for f in self.findings
            ],
        }

    def has_errors(self) -> bool:
        return self.summary.errors > 0


# DOC-PS-* stable codes per scripts/check_plugin_shape.py dimension (kind).
# Source of truth for kinds: scripts/check_plugin_shape.py ALL_KINDS.
# Folded into the machine contract (RA-073): the plugin_shape pass used to
# own these tables privately and keep them in sync by hand. The contract —
# not each pass — now owns the kind→code→severity mapping, so CI baselines
# and suppression rules import it from here.
# Keep in sync with docs/specs/0199-implementation-plan.md §5 P2-04.
PLUGIN_SHAPE_CODE_BY_KIND: dict[str, str] = {
    "missing_effects": "DOC-PS-001",
    "dual_form_residue": "DOC-PS-002",
    "duplicate_id": "DOC-PS-003",
    "plugin_location": "DOC-PS-004",
    "orphan_plugin": "DOC-PS-005",
    "dead_bundle_ref": "DOC-PS-006",
    "plugin_in_init": "DOC-PS-007",
}

# Severity bands mirror check_plugin_shape.py semantics:
#   * structural / contract violations = error (must fix)
#   * convention / orphan references = warning (should fix)
# Unknown kinds default to "info" (defensive; never fail-loud on a
# kind the doctor doesn't yet understand).
PLUGIN_SHAPE_SEVERITY_BY_KIND: dict[str, DoctorSeverity] = {
    "missing_effects": "error",
    "dual_form_residue": "error",
    "duplicate_id": "error",
    "plugin_location": "error",
    "orphan_plugin": "warning",
    "dead_bundle_ref": "warning",
    "plugin_in_init": "error",
}

# Fallback code for a violation kind the contract doesn't know yet.
PLUGIN_SHAPE_UNKNOWN_KIND_CODE: str = "DOC-PS-999"


__all__ = (
    "PLUGIN_SHAPE_CODE_BY_KIND",
    "PLUGIN_SHAPE_SEVERITY_BY_KIND",
    "PLUGIN_SHAPE_UNKNOWN_KIND_CODE",
    "DoctorDomain",
    "DoctorFinding",
    "DoctorReport",
    "DoctorSeverity",
    "DoctorSummary",
)
