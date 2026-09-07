"""Behavioral tests for ``web_to_contracts_report`` (ADR-0199 §5.3 / P2-11).

Per I-HPC-7 the adapter must be pure (no I/O, no journal writes) and
deterministic (C8). Each web ``HopVerdict`` (``H1..H8``) becomes a
contracts ``DoctorFinding`` with stable codes ``DOC-HTML-001..008``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from lca.contracts.diagnostics.doctor import (
    DoctorSummary,
)
from lca.plugins.transport.webserver.doctor.contracts_adapter import (
    web_to_contracts_report,
)
from lca.plugins.transport.webserver.doctor.models import (
    DoctorReport,
    HopVerdict,
)


def _make_web_report(
    *,
    run_id: str = "r_test",
    hops: dict[str, HopVerdict] | None = None,
) -> DoctorReport:
    """Build a minimal valid web DoctorReport with the given hops."""
    if hops is None:
        hops = {"H1": HopVerdict(ok=True, detail="ok")}
    return DoctorReport(
        schema="doctor.v3",
        run_id=run_id,
        trace_id="t_test",
        status="completed",
        outcome="completed",
        broken_hop=None,
        summary="ok",
        mode="backend",
        hops=hops,
        journal_path="journal.json",
        consistency={},
        factory={"ok": True, "tools_missing_plugin_state": []},
    )


# ─────────────── Hop verdict → severity mapping ───────────────


class TestHopFailureMapping:
    def test_web_h1_failure_becomes_error_finding(self) -> None:
        web_report = _make_web_report(
            hops={"H1": HopVerdict(ok=False, detail="journal.json missing")},
        )
        report = web_to_contracts_report(web_report)

        assert len(report.findings) == 1
        finding = report.findings[0]
        assert finding.severity == "error"
        assert finding.code == "DOC-HTML-001"
        assert "journal.json missing" in finding.message
        assert finding.remediation == "journal.json missing"
        assert finding.owner == "ADR-0199"
        assert finding.plugin_id is None
        assert finding.plan_ref is None


class TestHopSuccessMapping:
    def test_web_h1_success_becomes_info_finding(self) -> None:
        web_report = _make_web_report(
            hops={"H1": HopVerdict(ok=True, detail="ok")},
        )
        report = web_to_contracts_report(web_report)

        assert len(report.findings) == 1
        finding = report.findings[0]
        assert finding.severity == "info"
        assert finding.code == "DOC-HTML-001"
        assert "ok" in finding.message
        # Success remediation stays "No action required." even with detail set.
        assert finding.remediation == "No action required."


class TestHopUnevaluatedMapping:
    def test_web_h1_unevaluated_becomes_info_finding(self) -> None:
        web_report = _make_web_report(
            hops={"H1": HopVerdict(ok=None, detail="not evaluated")},
        )
        report = web_to_contracts_report(web_report)

        finding = report.findings[0]
        assert finding.severity == "info"
        assert finding.code == "DOC-HTML-001"
        assert "not evaluated" in finding.message


# ─────────────── Hop code mapping completeness ───────────────


class TestHopCodeMapping:
    def test_hop_code_mapping_complete(self) -> None:
        hops = {
            "H1": HopVerdict(ok=True, detail="ok"),
            "H2": HopVerdict(ok=True, detail="ok"),
            "H3": HopVerdict(ok=True, detail="ok"),
            "H4": HopVerdict(ok=True, detail="ok"),
            "H5": HopVerdict(ok=True, detail="ok"),
            "H6": HopVerdict(ok=True, detail="ok"),
            "H7": HopVerdict(ok=True, detail="ok"),
            "H8": HopVerdict(ok=True, detail="ok"),
        }
        web_report = _make_web_report(hops=hops)
        report = web_to_contracts_report(web_report)

        codes = {f.code for f in report.findings}
        assert codes == {
            "DOC-HTML-001",
            "DOC-HTML-002",
            "DOC-HTML-003",
            "DOC-HTML-004",
            "DOC-HTML-005",
            "DOC-HTML-006",
            "DOC-HTML-007",
            "DOC-HTML-008",
        }

    def test_unknown_hop_gets_doc_html_999_fallback(self) -> None:
        web_report = _make_web_report(
            hops={"H999": HopVerdict(ok=True, detail="ok")},
        )
        report = web_to_contracts_report(web_report)

        assert report.findings[0].code == "DOC-HTML-999"


# ─────────────── Subject + summary wiring ───────────────


class TestSubjectAndSummary:
    def test_contracts_report_subject_is_run_id(self) -> None:
        web_report = _make_web_report(run_id="r_alpha")
        report = web_to_contracts_report(web_report)
        assert report.subject == "r_alpha"

    def test_contracts_report_summary_matches_findings(self) -> None:
        hops = {
            "H1": HopVerdict(ok=False, detail="missing journal"),
            "H2": HopVerdict(ok=True, detail="ok"),
            "H3": HopVerdict(ok=None, detail="not evaluated"),
        }
        web_report = _make_web_report(hops=hops)
        report = web_to_contracts_report(web_report)

        assert report.summary.total == 3
        assert report.summary.errors == 1
        assert report.summary.warnings == 0
        assert report.summary.info == 2

    def test_activation_ref_propagated_when_passed(self) -> None:
        web_report = _make_web_report()
        report = web_to_contracts_report(web_report, activation_ref="plan-ref-xyz")
        assert report.activation_ref == "plan-ref-xyz"

    def test_activation_ref_defaults_to_none(self) -> None:
        web_report = _make_web_report()
        report = web_to_contracts_report(web_report)
        assert report.activation_ref is None


# ─────────────── Architectural purity ───────────────


class TestAdapterPurity:
    def test_findings_tuple_is_frozen(self) -> None:
        web_report = _make_web_report()
        report = web_to_contracts_report(web_report)
        assert isinstance(report.findings, tuple)
        # DoctorReport is frozen: any mutation must raise.
        with pytest.raises(FrozenInstanceError):
            report.activation_ref = "mutated"  # type: ignore[misc]

    def test_no_io_side_effects(self) -> None:
        """Adapter module must not import any I/O / environment module."""
        import lca.plugins.transport.webserver.doctor.contracts_adapter as module

        source = module.__file__
        assert source is not None
        with open(source, encoding="utf-8") as fh:
            text = fh.read()
        for forbidden in (
            "import subprocess",
            "import os",
            "from os",
            "import pathlib",
            "import requests",
            "import urllib",
        ):
            assert forbidden not in text, (
                f"contracts_adapter must stay pure; found forbidden token {forbidden!r}"
            )

    def test_does_not_mutate_input_web_report(self) -> None:
        web_report = _make_web_report(
            hops={"H1": HopVerdict(ok=False, detail="missing journal")},
        )
        snapshot_before = repr(web_report)
        web_to_contracts_report(web_report)
        # Web DoctorReport is frozen so this is a structural assertion:
        # repr must be identical and assignment must still raise.
        assert repr(web_report) == snapshot_before
        with pytest.raises(FrozenInstanceError):
            web_report.run_id = "mutated"  # type: ignore[misc]

    def test_empty_hops_yields_empty_findings(self) -> None:
        web_report = _make_web_report(hops={})
        report = web_to_contracts_report(web_report)

        assert report.findings == ()
        assert report.summary == DoctorSummary(total=0, errors=0, warnings=0, info=0)


# ─────────────── JSON round-trip ───────────────


class TestJsonableShape:
    def test_to_jsonable_matches_contract_shape(self) -> None:
        web_report = _make_web_report(
            run_id="r_json",
            hops={
                "H1": HopVerdict(ok=True, detail="ok"),
                "H2": HopVerdict(ok=False, detail="step closure incomplete"),
            },
        )
        contracts_doc = web_to_contracts_report(web_report, activation_ref="plan-1")
        payload = contracts_doc.to_jsonable()

        assert payload["subject"] == "r_json"
        assert payload["activation_ref"] == "plan-1"
        assert payload["summary"]["total"] == 2
        assert payload["summary"]["errors"] == 1
        assert payload["summary"]["warnings"] == 0
        assert payload["summary"]["info"] == 1
        assert isinstance(payload["findings"], list)
        assert len(payload["findings"]) == 2
