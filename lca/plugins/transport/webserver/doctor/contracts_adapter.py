"""Adapter: web DoctorReport → contracts DoctorReport (ADR-0199 §5.3 / P2-11).

Per ADR-0199 §5.3 the web ``GET /runs/{id}/doctor`` endpoint is one of
three canonical doctor consumers (CLI / CI / Web). Per the implementation
plan §5 P2-11 this endpoint should consume the contracts-layer
``DoctorReport`` shape (``lca/contracts/diagnostics/doctor.py``) so
external tooling can use one schema across CLI / CI / web.

This adapter is the seam that converts the existing web
``DoctorReport`` (with H1-H8 hops) into the contracts-layer report.
The existing web doctor internals are unchanged; the adapter is only
invoked when the query parameter ``?shape=contracts`` is present.

Per ADR-0199 I-HPC-7 (Doctor 只读): pure projection, no I/O, no journal
writes, no K3 fiber setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
    DoctorSeverity,
    DoctorSummary,
)

if TYPE_CHECKING:
    from lca.plugins.transport.webserver.doctor.models import (
        DoctorReport as WebDoctorReport,
    )


_OWNER_ADR: str = "ADR-0199"

# Stable code prefixes per hop — DOC-HTML-NNN where HTML = H1..H8
# (avoiding DOC-PG/CAP/PRIV/PS/COMPAT to not collide with other passes)
_HOP_CODES: dict[str, str] = {
    "H1": "DOC-HTML-001",  # journal.json exists + readable
    "H2": "DOC-HTML-002",  # step closure completeness
    "H3": "DOC-HTML-003",  # step ordering continuity
    "H4": "DOC-HTML-004",  # UI-mode: browser reachability
    "H5": "DOC-HTML-005",  # UI-mode: rendering
    "H6": "DOC-HTML-006",  # observable output / file
    "H7": "DOC-HTML-007",  # tool success rate
    "H8": "DOC-HTML-008",  # step causal chain (ADR-0164 Phase 4)
}

_UNEVALUATED_DETAIL = "not evaluated"


def web_to_contracts_report(
    web_report: WebDoctorReport,
    *,
    activation_ref: str | None = None,
) -> DoctorReport:
    """Convert the web DoctorReport (H1-H8 hops) → contracts DoctorReport.

    Each H1-H8 hop becomes a DoctorFinding with:
      - code: ``DOC-HTML-NNN`` (where NNN is the hop number)
      - severity: derived from hop.ok (False=error, None=info, True=info "ok")
      - message: hop.detail (or "ok" / "not evaluated" for empty)
      - remediation: derived from the hop's intent
      - plugin_id: None (web doctor is per-run, not per-plugin)

    Per I-HPC-7: pure projection — no I/O, no journal writes.
    """
    findings: list[DoctorFinding] = []

    for hop_name, hop_value in web_report.hops.items():
        code = _HOP_CODES.get(hop_name, "DOC-HTML-999")
        if hop_value is None or hop_value.ok is None:
            severity: DoctorSeverity = "info"
            message = f"{hop_name}: {_UNEVALUATED_DETAIL}"
        elif hop_value.ok is False:
            severity = "error"
            message = f"{hop_name}: {hop_value.detail or 'failed'}"
        elif hop_value.ok is True:
            severity = "info"
            message = f"{hop_name}: {hop_value.detail or 'ok'}"
        else:  # pragma: no cover (defensive)
            severity = "info"
            message = f"{hop_name}: unknown state"

        remediation = (
            hop_value.detail
            if hop_value.ok is False and hop_value.detail
            else "No action required."
        )

        findings.append(
            DoctorFinding(
                code=code,
                severity=severity,
                owner=_OWNER_ADR,
                message=message,
                remediation=remediation,
                plugin_id=None,
                plan_ref=None,
            )
        )

    # Subject: web doctor has run_id; use it
    subject = getattr(web_report, "run_id", None) or "web_run"

    # Compute summary
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    info = sum(1 for f in findings if f.severity == "info")
    summary = DoctorSummary(
        total=len(findings),
        errors=errors,
        warnings=warnings,
        info=info,
    )

    return DoctorReport(
        subject=subject,
        findings=tuple(findings),
        summary=summary,
        activation_ref=activation_ref,
    )


__all__ = ("web_to_contracts_report",)
