"""Behavioral tests for ``lca.contracts.diagnostics.doctor``.

Covers PR-0199-P2-01 (DoctorFinding + severity) and PR-0199-P2-02
(DoctorReport aggregate) — pure contracts, no I/O.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from lca.contracts.diagnostics.doctor import (
    DoctorDomain,
    DoctorFinding,
    DoctorReport,
    DoctorSeverity,
    DoctorSummary,
)

_VALID_CODES = (
    "DOC-PS-001",
    "DOC-CAP-001",
    "DOC-PG-001",
    "DOC-PRIV-001",
    "DOC-RES-001",
    "DOC-TRUST-001",
    "DOC-COMPAT-001",
)


def _minimal_finding(**overrides: object) -> DoctorFinding:
    """Build a minimal valid DoctorFinding, applying keyword overrides."""
    base: dict[str, object] = {
        "code": "DOC-PS-001",
        "severity": "warning",
        "owner": "ADR-0199",
        "message": "demo plugin shape mismatch",
        "remediation": "rename plugin id to match manifest",
    }
    base.update(overrides)
    return DoctorFinding(**base)  # type: ignore[arg-type]


# ─────────────── DoctorFinding ───────────────


class TestDoctorFindingCodePattern:
    @pytest.mark.parametrize("code", _VALID_CODES)
    def test_finding_code_pattern_valid(self, code: str) -> None:
        finding = _minimal_finding(code=code)
        assert finding.code == code

    def test_finding_code_pattern_invalid_short(self) -> None:
        # `DOC-PS-1` violates the 3-digit minimum.
        with pytest.raises(ValueError, match="DOC-<DOMAIN>-<NNN>"):
            _minimal_finding(code="DOC-PS-1")

    def test_finding_code_pattern_invalid_lowercase(self) -> None:
        # Domain must be uppercase.
        with pytest.raises(ValueError, match="DOC-<DOMAIN>-<NNN>"):
            _minimal_finding(code="DOC-ps-001")

    def test_finding_code_pattern_invalid_no_prefix(self) -> None:
        # Without the DOC- prefix the regex cannot match.
        with pytest.raises(ValueError, match="DOC-<DOMAIN>-<NNN>"):
            _minimal_finding(code="PS-001")


class TestDoctorFindingSeverity:
    @pytest.mark.parametrize("severity", ["error", "warning", "info"])
    def test_finding_severity_valid(self, severity: DoctorSeverity) -> None:
        finding = _minimal_finding(severity=severity)
        assert finding.severity == severity

    def test_finding_severity_invalid(self) -> None:
        with pytest.raises(ValueError, match="severity"):
            _minimal_finding(severity="critical")  # type: ignore[arg-type]


class TestDoctorFindingRequiredStrings:
    def test_finding_message_required(self) -> None:
        with pytest.raises(ValueError, match="message"):
            _minimal_finding(message="")

    def test_finding_remediation_required(self) -> None:
        with pytest.raises(ValueError, match="remediation"):
            _minimal_finding(remediation="")


class TestDoctorFindingFrozen:
    def test_finding_frozen(self) -> None:
        finding = _minimal_finding()
        with pytest.raises(FrozenInstanceError):
            finding.code = "DOC-PS-999"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            finding.severity = "error"  # type: ignore[misc]


# ─────────────── DoctorSummary ───────────────


class TestDoctorSummary:
    def test_summary_inconsistent_counts_rejected(self) -> None:
        # total != errors + warnings + info
        with pytest.raises(ValueError, match="inconsistent"):
            DoctorSummary(total=5, errors=1, warnings=1, info=1)

    def test_summary_negative_counts_rejected(self) -> None:
        with pytest.raises(ValueError, match=">= 0"):
            DoctorSummary(total=-1, errors=0, warnings=0, info=0)
        with pytest.raises(ValueError, match=">= 0"):
            DoctorSummary(total=2, errors=-1, warnings=2, info=1)

    def test_summary_valid_zero(self) -> None:
        summary = DoctorSummary(total=0, errors=0, warnings=0, info=0)
        assert summary.total == 0
        assert summary.errors == 0


# ─────────────── DoctorReport ───────────────


class TestDoctorReportConstruction:
    def test_report_subject_required(self) -> None:
        with pytest.raises(ValueError, match="subject"):
            DoctorReport.from_findings("", [])

    def test_report_summary_matches_findings(self) -> None:
        findings = (
            _minimal_finding(severity="error"),
            _minimal_finding(code="DOC-PS-002", severity="warning"),
        )
        # Hand-craft a summary that disagrees with the actual findings.
        bad_summary = DoctorSummary(total=2, errors=2, warnings=0, info=0)
        with pytest.raises(ValueError, match="summary mismatch"):
            DoctorReport(
                subject="/profiles/x.yaml",
                findings=findings,
                summary=bad_summary,
            )

    def test_report_from_findings_auto_summary(self) -> None:
        findings = (
            _minimal_finding(severity="error", code="DOC-PS-001"),
            _minimal_finding(severity="error", code="DOC-PS-002"),
            _minimal_finding(severity="warning", code="DOC-PS-003"),
            _minimal_finding(severity="info", code="DOC-PS-004"),
        )
        report = DoctorReport.from_findings(
            "/profiles/agent.yaml",
            findings,
            activation_ref="plan-ref-1",
        )
        assert report.subject == "/profiles/agent.yaml"
        assert report.summary.total == 4
        assert report.summary.errors == 2
        assert report.summary.warnings == 1
        assert report.summary.info == 1
        assert report.activation_ref == "plan-ref-1"
        assert report.findings == findings


class TestDoctorReportErrors:
    def test_report_has_errors_true_when_error_present(self) -> None:
        report = DoctorReport.from_findings(
            "/profiles/x.yaml",
            [_minimal_finding(severity="error")],
        )
        assert report.has_errors() is True

    def test_report_has_errors_false_when_no_errors(self) -> None:
        report = DoctorReport.from_findings(
            "/profiles/x.yaml",
            [
                _minimal_finding(severity="warning"),
                _minimal_finding(severity="info", code="DOC-PS-002"),
            ],
        )
        assert report.has_errors() is False


# ─────────────── DoctorReport.to_jsonable ───────────────


class TestDoctorReportJsonProjection:
    def test_report_to_jsonable_shape(self) -> None:
        findings = (
            _minimal_finding(severity="error", plugin_id="demo.plugin"),
            _minimal_finding(
                code="DOC-PS-002",
                severity="warning",
                plugin_id="demo.plugin",
                plan_ref="plan-abc",
            ),
        )
        report = DoctorReport.from_findings(
            "/profiles/x.yaml",
            findings,
            activation_ref="plan-abc",
        )
        payload = report.to_jsonable()
        assert set(payload.keys()) == {
            "subject",
            "activation_ref",
            "summary",
            "findings",
        }
        assert payload["subject"] == "/profiles/x.yaml"
        assert payload["activation_ref"] == "plan-abc"
        assert payload["summary"] == {
            "total": 2,
            "errors": 1,
            "warnings": 1,
            "info": 0,
        }
        assert isinstance(payload["findings"], list)
        assert len(payload["findings"]) == 2
        finding0 = payload["findings"][0]
        assert set(finding0.keys()) == {
            "code",
            "severity",
            "owner",
            "message",
            "remediation",
            "plugin_id",
            "plan_ref",
        }
        assert finding0["code"] == "DOC-PS-001"
        assert finding0["severity"] == "error"
        # Must be JSON-serializable as-is — no Python-specific objects leak out.
        encoded = json.dumps(payload)
        assert json.loads(encoded) == payload

    def test_report_to_jsonable_empty_findings(self) -> None:
        report = DoctorReport.from_findings("/profiles/empty.yaml", [])
        payload = report.to_jsonable()
        assert payload["subject"] == "/profiles/empty.yaml"
        assert payload["activation_ref"] is None
        assert payload["summary"] == {
            "total": 0,
            "errors": 0,
            "warnings": 0,
            "info": 0,
        }
        assert payload["findings"] == []


# ─────────────── Architectural purity ───────────────


class TestDoctorModulePurity:
    def test_report_no_io_imports(self) -> None:
        """Doctor must be pure contracts — no subprocess, pathlib, or os."""
        import lca.contracts.diagnostics.doctor as module

        source = module.__file__
        assert source is not None
        with open(source, encoding="utf-8") as fh:
            text = fh.read()
        # Disallowed I/O / environment modules.
        for forbidden in ("import subprocess", "import os", "from os", "import pathlib"):
            assert forbidden not in text, (
                f"doctor.py must stay pure; found forbidden token {forbidden!r}"
            )


# ─────────────── Type-hint sanity ───────────────


class TestDoctorDomainLiteral:
    def test_domain_literal_set(self) -> None:
        assert set(DoctorDomain.__args__) == {
            "PS",
            "CAP",
            "PG",
            "PRIV",
            "RES",
            "TRUST",
            "COMPAT",
        }

    def test_severity_literal_set(self) -> None:
        assert set(DoctorSeverity.__args__) == {"error", "warning", "info"}
