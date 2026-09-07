"""Behavioral tests for the ProfileCompileDryRun doctor pass (PR-0199-P2-03).

Per ADR-0199 §5.1 + §5.2 the doctor is a compile-pipeline projection. These
tests assert: no exception escapes for profile-level failures, every emitted
code matches DOC-XX-NNN, and the pass is deterministic (C8) + read-only
(I-HPC-7). Real profile files are NOT required; resolve_profile /
compile_plan are stubbed at the module boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from lca.harness.composition.plan_compiler import PlanCompilerError
from lca.harness.diagnostics.doctor.compile_dry_run import (
    DoctorCompileError,
    ProfileCompileDryRun,
)

# Stable machine-code regex copied verbatim from
# lca.contracts.diagnostics.doctor (DOC-<DOMAIN>-<NNN>).
_CODE_RE = re.compile(r"^DOC-[A-Z]{2,6}-\d{3,}$")


# ─────────── stubs ───────────


@dataclass(frozen=True)
class _FakeResolved:
    profile_path: str = "/fake/profile.yaml"


@dataclass(frozen=True)
class _FakePlan:
    profile_path: str = "/fake/profile.yaml"


@dataclass(frozen=True)
class _FakeResult:
    """Mimics PlanResolutionService.resolve_refs result shape (P1-07)."""

    plan_ref: str
    graph_ref: str = "graph-001"
    plugin_set_ref: str = "plugin-set-A"


_FAKE_PLAN_REF = "f" * 16  # 16-hex style id


def _ok_resolve(*_args: Any, **_kwargs: Any) -> _FakeResolved:
    return _FakeResolved()


def _ok_compile(*_args: Any, **_kwargs: Any) -> _FakePlan:
    return _FakePlan()


def _ok_plan_ref(*_args: Any, **_kwargs: Any) -> str:
    return _FAKE_PLAN_REF


# ─────────── tests ───────────


class TestInvalidInputs:
    """DoctorCompileError is raised ONLY for invalid inputs."""

    def test_run_with_none_path_raises_doctor_compile_error(self) -> None:
        doctor = ProfileCompileDryRun()
        with pytest.raises(DoctorCompileError):
            doctor.run(None)  # type: ignore[arg-type]

    def test_run_with_empty_path_raises_doctor_compile_error(self) -> None:
        doctor = ProfileCompileDryRun()
        with pytest.raises(DoctorCompileError):
            doctor.run("")


class TestSuccess:
    """resolve + compile both succeed → info finding with plan_ref."""

    def test_run_resolves_and_compiles_successfully(self) -> None:
        doctor = ProfileCompileDryRun()
        with (
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
                _ok_resolve,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compile_plan",
                _ok_compile,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compiled_run_plan_ref",
                _ok_plan_ref,
            ),
        ):
            report = doctor.run("/fake/profile.yaml")

        assert report.summary.errors == 0
        assert report.summary.warnings == 0
        assert report.summary.info == 1
        finding = report.findings[0]
        assert finding.severity == "info"
        assert finding.plan_ref == _FAKE_PLAN_REF

    def test_report_subject_is_profile_path_string(self) -> None:
        doctor = ProfileCompileDryRun()
        with (
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
                _ok_resolve,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compile_plan",
                _ok_compile,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compiled_run_plan_ref",
                _ok_plan_ref,
            ),
        ):
            report = doctor.run("/some/where/profile.yaml")

        assert report.subject == "/some/where/profile.yaml"

    def test_report_has_no_errors_on_success(self) -> None:
        doctor = ProfileCompileDryRun()
        with (
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
                _ok_resolve,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compile_plan",
                _ok_compile,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compiled_run_plan_ref",
                _ok_plan_ref,
            ),
        ):
            report = doctor.run("/fake/profile.yaml")

        assert report.has_errors() is False

    def test_report_carries_plan_ref_on_success(self) -> None:
        doctor = ProfileCompileDryRun()
        with (
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
                _ok_resolve,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compile_plan",
                _ok_compile,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compiled_run_plan_ref",
                _ok_plan_ref,
            ),
        ):
            report = doctor.run("/fake/profile.yaml")

        assert report.findings[0].plan_ref == _FAKE_PLAN_REF
        assert _FAKE_PLAN_REF in report.findings[0].message


class TestErrorTranslation:
    """Each exception class is converted into the right stable code."""

    def test_plan_compiler_error_becomes_doc_compat_001_finding(self) -> None:
        def _boom_compile(*_args: Any, **_kwargs: Any) -> _FakePlan:
            raise PlanCompilerError("phase binding missing: think")

        doctor = ProfileCompileDryRun()
        with (
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
                _ok_resolve,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compile_plan",
                _boom_compile,
            ),
        ):
            report = doctor.run("/fake/profile.yaml")

        assert report.summary.errors == 1
        finding = report.findings[0]
        assert finding.code == "DOC-COMPAT-001"
        assert finding.severity == "error"
        assert finding.plan_ref is None
        assert "phase binding missing" in finding.message

    def test_file_not_found_becomes_doc_compat_002_finding(self) -> None:
        def _missing_resolve(*_args: Any, **_kwargs: Any) -> _FakeResolved:
            raise FileNotFoundError("/nope/profile.yaml")

        doctor = ProfileCompileDryRun()
        with patch(
            "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
            _missing_resolve,
        ):
            report = doctor.run("/nope/profile.yaml")

        assert report.summary.errors == 1
        finding = report.findings[0]
        assert finding.code == "DOC-COMPAT-002"
        assert finding.severity == "error"
        assert finding.plan_ref is None

    def test_value_error_becomes_doc_compat_003_finding(self) -> None:
        def _bad_resolve(*_args: Any, **_kwargs: Any) -> _FakeResolved:
            raise ValueError("entry at index 0 missing id")

        doctor = ProfileCompileDryRun()
        with patch(
            "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
            _bad_resolve,
        ):
            report = doctor.run("/fake/profile.yaml")

        assert report.summary.errors == 1
        finding = report.findings[0]
        assert finding.code == "DOC-COMPAT-003"
        assert finding.severity == "error"
        assert finding.plan_ref is None
        assert "entry at index 0 missing id" in finding.message

    def test_no_io_side_effects_on_profile_failure(self) -> None:
        """Non-existent profile → report returned, no exception raised."""

        def _missing(*_args: Any, **_kwargs: Any) -> _FakeResolved:
            raise FileNotFoundError("/does/not/exist.yaml")

        doctor = ProfileCompileDryRun()
        with patch(
            "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
            _missing,
        ):
            # Must NOT raise; doctor must convert to finding.
            report = doctor.run("/does/not/exist.yaml")

        assert report.summary.total == 1
        assert report.summary.errors == 1


class TestInjection:
    """Service injection + fallback paths."""

    def test_falls_back_to_resolve_when_no_service_injected(self) -> None:
        doctor = ProfileCompileDryRun(plan_resolution_service=None)
        with (
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
                side_effect=_ok_resolve,
            ) as resolve_mock,
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compile_plan",
                side_effect=_ok_compile,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compiled_run_plan_ref",
                side_effect=_ok_plan_ref,
            ),
        ):
            report = doctor.run("/fake/profile.yaml")

        assert resolve_mock.called
        assert report.summary.errors == 0

    def test_uses_injected_service_when_provided(self) -> None:
        class _FakeService:
            def resolve_refs(
                self,
                profile_path: Any,
                *,
                session_id: Any,
            ) -> _FakeResult:
                assert session_id is None  # doctor is pre-activation
                return _FakeResult(plan_ref="srv" + _FAKE_PLAN_REF[3:])

        service = _FakeService()
        doctor = ProfileCompileDryRun(plan_resolution_service=service)
        # resolve_profile / compile_plan must NOT be called when service
        # is injected.
        with (
            patch("lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile") as resolve_mock,
            patch("lca.harness.diagnostics.doctor.compile_dry_run.compile_plan") as compile_mock,
        ):
            report = doctor.run("/fake/profile.yaml")

        assert resolve_mock.call_count == 0
        assert compile_mock.call_count == 0
        assert report.findings[0].plan_ref == "srv" + _FAKE_PLAN_REF[3:]


class TestDeterminism:
    """C8 — same inputs → same outputs."""

    def test_session_id_never_affects_doctor_output(self) -> None:
        """Doctor passes session_id=None deterministically (pre-activation)."""

        captured_session_ids: list[Any] = []

        class _CapturingService:
            def resolve_refs(
                self,
                profile_path: Any,
                *,
                session_id: Any,
            ) -> _FakeResult:
                captured_session_ids.append(session_id)
                return _FakeResult(plan_ref=_FAKE_PLAN_REF)

        service = _CapturingService()
        doctor = ProfileCompileDryRun(plan_resolution_service=service)
        for _ in range(3):
            doctor.run("/fake/profile.yaml")

        assert captured_session_ids == [None, None, None]

    def test_same_input_same_output(self) -> None:
        doctor = ProfileCompileDryRun()
        with (
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
                _ok_resolve,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compile_plan",
                _ok_compile,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compiled_run_plan_ref",
                _ok_plan_ref,
            ),
        ):
            a = doctor.run("/fake/profile.yaml")
            b = doctor.run("/fake/profile.yaml")

        assert a.to_jsonable() == b.to_jsonable()


class TestCodeConformance:
    """Every emitted code matches the stable machine-code pattern."""

    def test_code_regex_compliance(self) -> None:
        """All codes from all paths match DOC-XX-NNN."""

        def _raise_value(*_args: Any, **_kwargs: Any) -> _FakeResolved:
            raise ValueError("anything")

        def _raise_compile(*_args: Any, **_kwargs: Any) -> _FakePlan:
            raise PlanCompilerError("anything")

        def _raise_fnf(*_args: Any, **_kwargs: Any) -> _FakeResolved:
            raise FileNotFoundError("/x")

        doctor = ProfileCompileDryRun()

        # Path 1: success.
        with (
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
                _ok_resolve,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compile_plan",
                _ok_compile,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compiled_run_plan_ref",
                _ok_plan_ref,
            ),
        ):
            ok_report = doctor.run("/fake/profile.yaml")

        # Path 2: PlanCompilerError.
        with (
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
                _ok_resolve,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compile_plan",
                _raise_compile,
            ),
        ):
            compile_report = doctor.run("/fake/profile.yaml")

        # Path 3: ValueError (resolve error).
        with patch(
            "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
            _raise_value,
        ):
            value_report = doctor.run("/fake/profile.yaml")

        # Path 4: FileNotFoundError.
        with patch(
            "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
            _raise_fnf,
        ):
            fnf_report = doctor.run("/fake/profile.yaml")

        for report in (ok_report, compile_report, value_report, fnf_report):
            for finding in report.findings:
                assert _CODE_RE.match(finding.code), (
                    f"code {finding.code!r} does not match DOC-<DOMAIN>-<NNN>"
                )
                assert finding.severity in ("error", "warning", "info")
                assert finding.owner == "ADR-0199"
                assert finding.message
                assert finding.remediation  # even info findings need remediation

    def test_info_finding_remediation_is_non_empty(self) -> None:
        """DoctorFinding.__post_init__ enforces non-empty remediation."""
        doctor = ProfileCompileDryRun()
        with (
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.resolve_profile",
                _ok_resolve,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compile_plan",
                _ok_compile,
            ),
            patch(
                "lca.harness.diagnostics.doctor.compile_dry_run.compiled_run_plan_ref",
                _ok_plan_ref,
            ),
        ):
            report = doctor.run("/fake/profile.yaml")

        # The info finding must carry a non-empty remediation string
        # (DoctorFinding.__post_init__ would have raised otherwise).
        assert report.findings[0].remediation != ""
