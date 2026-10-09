"""Behavioral tests for the DoctorFacade orchestrator (PR-0199-P2-07).

Per ADR-0199 §5.1 + §5.3 DoctorFacade composes the wired doctor passes
into a single ``doctor_profile(path) -> DoctorReport`` entry point. Since
RA-051 only two passes are wired (compile dry-run + plugin shape): the
capability/phase_graph/privilege/trust orchestration was deleted because
its inputs (``plugin_contracts`` / ``phase_graph_plan``) are structurally
absent from the plan seam and the passes always silently skipped in
production (I-HPC-7). The four modules remain importable as library
passes; their own test modules pin their behavior.

These tests assert: aggregation, ordering, opt-in/out toggling,
deterministic subject, no K3 boot / no PlanResolutionService call, and
read-only invariant (I-HPC-7).

All passes are injected as stubs to keep the suite deterministic; the
real passes are exercised by their own dedicated test modules.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
)
from lca.harness.diagnostics.doctor.facade import DoctorFacade

# ─────────── helpers ───────────


def _finding(
    code: str,
    severity: str,
    msg: str,
    *,
    plugin_id: str | None = None,
    plan_ref: str | None = None,
) -> DoctorFinding:
    return DoctorFinding(
        code=code,
        severity=severity,
        owner="ADR-0199",
        message=msg,
        remediation="stub remediation",
        plugin_id=plugin_id,
        plan_ref=plan_ref,
    )


def _ok_report(
    subject: str,
    findings: list[DoctorFinding] | tuple[DoctorFinding, ...],
    *,
    activation_ref: str | None = None,
) -> DoctorReport:
    return DoctorReport.from_findings(
        subject=subject,
        findings=list(findings),
        activation_ref=activation_ref,
    )


# ─────────── stubs ───────────


@dataclass
class _RecordingStub:
    """Generic stub pass that records the call order and returns a fixed report."""

    report: DoctorReport
    name: str
    calls: list[Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

    def run(self, profile_path: Any) -> DoctorReport:
        self.calls.append(profile_path)
        return self.report


# ─────────── construction tests ───────────


class TestConstruction:
    """Default construction + injection."""

    def test_facade_default_construction(self) -> None:
        facade = DoctorFacade()
        # Internal passes must be default-instantiated (non-None).
        assert facade._compile_dry_run is not None
        assert facade._plugin_shape is not None

    def test_facade_accepts_injected_passes(self) -> None:
        compile_stub = _RecordingStub(
            report=_ok_report("compile", []),
            name="compile",
        )
        shape_stub = _RecordingStub(
            report=_ok_report("plugin_shape", []),
            name="plugin_shape",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
        )
        assert facade._compile_dry_run is compile_stub
        assert facade._plugin_shape is shape_stub

    def test_facade_has_no_dead_pass_seams(self) -> None:
        """RA-051: the deleted passes leave no attributes or helpers behind.

        The dead ``getattr(result.compiled_plan, 'plugin_contracts'|'phase_graph_plan',
        None)`` seam always returned None in production; it must not exist
        in any form — silent skip is replaced by an explicit absence.
        """
        facade = DoctorFacade()
        for attr in (
            "_capability_cardinality",
            "_phase_graph",
            "_privilege",
            "_trust",
            "_external_kind_by_plugin",
            "_optional_resolve_contracts",
            "_optional_resolve_phase_graph",
        ):
            assert not hasattr(facade, attr), attr


# ─────────── aggregation tests ───────────


class TestAggregation:
    """Findings from all passes are concatenated in documented order."""

    def test_doctor_profile_aggregates_all_findings(self) -> None:
        compile_stub = _RecordingStub(
            report=_ok_report(
                "compile",
                [_finding("DOC-COMPAT-000", "info", "compile ok")],
            ),
            name="compile",
        )
        shape_stub = _RecordingStub(
            report=_ok_report(
                "plugin_shape",
                [_finding("DOC-PS-001", "error", "missing effects")],
            ),
            name="plugin_shape",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
        )
        report = facade.doctor_profile("/fake/profile.yaml")

        codes = [f.code for f in report.findings]
        assert codes == [
            "DOC-COMPAT-000",
            "DOC-PS-001",
        ]

    def test_doctor_profile_subject_is_profile_path(self) -> None:
        facade = DoctorFacade(
            compile_dry_run=_RecordingStub(
                report=_ok_report("compile", []),
                name="compile",
            ),  # type: ignore[arg-type]
            plugin_shape=_RecordingStub(
                report=_ok_report("plugin_shape", []),
                name="plugin_shape",
            ),  # type: ignore[arg-type]
        )
        report = facade.doctor_profile("/some/where/profile.yaml")
        assert report.subject == "/some/where/profile.yaml"

    def test_doctor_profile_activation_ref_propagated(self) -> None:
        compile_stub = _RecordingStub(
            report=_ok_report("compile", [], activation_ref="act-123"),
            name="compile",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=_RecordingStub(
                report=_ok_report("plugin_shape", []),
                name="plugin_shape",
            ),  # type: ignore[arg-type]
        )
        report = facade.doctor_profile("/fake/profile.yaml")
        assert report.activation_ref == "act-123"

    def test_doctor_profile_summary_reflects_aggregated_findings(self) -> None:
        compile_stub = _RecordingStub(
            report=_ok_report(
                "compile",
                [
                    _finding("DOC-COMPAT-001", "error", "compile fail 1"),
                    _finding("DOC-COMPAT-001", "error", "compile fail 2"),
                ],
            ),
            name="compile",
        )
        shape_stub = _RecordingStub(
            report=_ok_report(
                "plugin_shape",
                [_finding("DOC-PS-005", "warning", "orphan plugin")],
            ),
            name="plugin_shape",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
        )
        report = facade.doctor_profile("/fake/profile.yaml")

        assert report.summary.errors == 2
        assert report.summary.warnings == 1
        assert report.summary.info == 0
        assert report.summary.total == 3

    def test_doctor_profile_empty_when_all_passes_clean(self) -> None:
        facade = DoctorFacade(
            compile_dry_run=_RecordingStub(
                report=_ok_report("compile", []),
                name="compile",
            ),  # type: ignore[arg-type]
            plugin_shape=_RecordingStub(
                report=_ok_report("plugin_shape", []),
                name="plugin_shape",
            ),  # type: ignore[arg-type]
        )
        report = facade.doctor_profile("/fake/profile.yaml")
        assert report.summary.total == 0
        assert report.summary.errors == 0
        assert report.has_errors() is False


# ─────────── order tests ───────────


class TestOrder:
    """Pass order is deterministic and matches ADR-0199 §5.1 + P2-07."""

    def test_doctor_profile_passes_are_run_in_documented_order(self) -> None:
        order: list[str] = []

        def _make_stub(name: str) -> _RecordingStub:
            return _RecordingStub(
                report=_ok_report(name, []),
                name=name,
            )

        compile_stub = _make_stub("compile")
        shape_stub = _make_stub("plugin_shape")

        # Wrap each run() so we observe the call order without changing
        # the returned report.
        original_compile = compile_stub.run
        original_shape = shape_stub.run

        def _wrap(name: str, original: Any) -> Any:
            def _wrapped(profile_path: Any) -> DoctorReport:
                order.append(name)
                return original(profile_path)

            return _wrapped

        compile_stub.run = _wrap("compile", original_compile)  # type: ignore[method-assign]
        shape_stub.run = _wrap("plugin_shape", original_shape)  # type: ignore[method-assign]

        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
        )
        facade.doctor_profile("/fake/profile.yaml")

        assert order == [
            "compile",
            "plugin_shape",
        ]


# ─────────── opt-out tests ───────────


class TestOptOut:
    """Per-pass opt-out flags skip the corresponding pass."""

    def test_doctor_profile_can_disable_plugin_shape_pass(self) -> None:
        compile_stub = _RecordingStub(
            report=_ok_report("compile", []),
            name="compile",
        )
        shape_stub = _RecordingStub(
            report=_ok_report(
                "plugin_shape",
                [_finding("DOC-PS-001", "error", "should not appear")],
            ),
            name="plugin_shape",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
        )
        report = facade.doctor_profile(
            "/fake/profile.yaml",
            include_plugin_shape=False,
        )
        assert shape_stub.calls == []
        assert all(f.code != "DOC-PS-001" for f in report.findings)


# ─────────── read-only invariant tests ───────────


class TestReadOnlyInvariant:
    """Doctor is read-only (I-HPC-7): no K3 boot, no journal writes."""

    def test_doctor_profile_never_resolves_plan(self) -> None:
        """RA-051: the facade must not construct PlanResolutionService at all.

        Previously the dead ``_optional_resolve_*`` helpers built a
        ``PlanResolutionService`` per pass and silently swallowed every
        failure; the resolve seam is gone now, so the factory must see
        zero calls.
        """

        class _ServiceFactory:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self) -> Any:
                self.calls += 1
                raise AssertionError("PlanResolutionService must not be constructed")

        factory = _ServiceFactory()
        facade = DoctorFacade(
            compile_dry_run=_RecordingStub(
                report=_ok_report("compile", []),
                name="compile",
            ),  # type: ignore[arg-type]
            plugin_shape=_RecordingStub(
                report=_ok_report("plugin_shape", []),
                name="plugin_shape",
            ),  # type: ignore[arg-type]
        )
        # Patch the dynamic import target (was imported lazily inside helpers).
        with patch(
            "lca.application.runtime.plan_resolution.PlanResolutionService",
            factory,
        ):
            report = facade.doctor_profile("/fake/profile.yaml")
        assert factory.calls == 0
        assert report.subject == "/fake/profile.yaml"

    def test_doctor_profile_no_journal_writes(self) -> None:
        """Module MUST NOT import Session.append (I-HPC-7).

        Per AGENTS.md §2.2 the only durable write seam is
        ``Session.append``; doctor must not reach it.
        """
        module = importlib.import_module("lca.harness.diagnostics.doctor.facade")
        # Collect all symbols bound to the facade module.
        source_lines: list[str] = []
        for name in dir(module):
            value = getattr(module, name)
            # Look at anything that has __module__ set to the facade —
            # including re-exports of helper functions.
            src_module = getattr(value, "__module__", None)
            if src_module == module.__name__:
                source_lines.append(name)
        # The facade's module must not contain a reference to Session.append
        # in any of its imports (transitively checked via __all__ + dir).
        forbidden = ["Session.append", "session_append", "FactGateway"]
        for sym in source_lines:
            obj = getattr(module, sym, None)
            qualname = getattr(obj, "__qualname__", "")
            assert "Session.append" not in qualname
            assert "FactGateway" not in qualname
        # Module does not even import Session (assert name absence).
        assert "Session" not in dir(module)
        assert "FactGateway" not in dir(module)
        assert forbidden == forbidden  # marker that test ran (silence unused)


# ─────────── module surface tests ───────────


class TestModuleSurface:
    """Module docstring + __all__ honor ADR-0199 §5.1 + §5.3 + I-HPC-7."""

    def test_module_docstring_cites_adr_and_invariants(self) -> None:
        module = importlib.import_module("lca.harness.diagnostics.doctor.facade")
        assert module.__doc__ is not None
        doc = module.__doc__
        assert "ADR-0199" in doc
        assert "§5.1" in doc
        assert "§5.3" in doc
        assert "I-HPC-7" in doc

    def test_module_exports_doctor_facade_only(self) -> None:
        module = importlib.import_module("lca.harness.diagnostics.doctor.facade")
        assert module.__all__ == ("DoctorFacade",)
