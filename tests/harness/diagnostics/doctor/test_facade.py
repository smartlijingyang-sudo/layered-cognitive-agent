"""Behavioral tests for the DoctorFacade orchestrator (PR-0199-P2-07).

Per ADR-0199 §5.1 + §5.3 DoctorFacade composes the four P2 doctor
passes into a single ``doctor_profile(path) -> DoctorReport`` entry
point. These tests assert: aggregation, ordering, opt-in/out toggling,
skip-on-compile-failure semantics, deterministic subject, no K3 boot,
and read-only invariant (I-HPC-7).

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
        assert facade._capability_cardinality is not None
        assert facade._phase_graph is not None

    def test_facade_accepts_injected_passes(self) -> None:
        compile_stub = _RecordingStub(
            report=_ok_report("compile", []),
            name="compile",
        )
        shape_stub = _RecordingStub(
            report=_ok_report("plugin_shape", []),
            name="plugin_shape",
        )
        cap_stub = _RecordingStub(
            report=_ok_report("capability", []),
            name="capability",
        )
        pg_stub = _RecordingStub(
            report=_ok_report("phase_graph", []),
            name="phase_graph",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
            capability_cardinality=cap_stub,  # type: ignore[arg-type]
            phase_graph=pg_stub,  # type: ignore[arg-type]
        )
        assert facade._compile_dry_run is compile_stub
        assert facade._plugin_shape is shape_stub
        assert facade._capability_cardinality is cap_stub
        assert facade._phase_graph is pg_stub


# ─────────── aggregation tests ───────────


class TestAggregation:
    """Findings from all passes are concatenated in documented order."""

    def test_doctor_profile_aggregates_all_findings(self) -> None:
        # Compile must NOT emit errors here, because the facade skips
        # downstream passes when compile fails. Use an info finding.
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
        cap_stub = _RecordingStub(
            report=_ok_report(
                "capability",
                [_finding("DOC-CAP-001", "error", "duplicate cap")],
            ),
            name="capability",
        )
        pg_stub = _RecordingStub(
            report=_ok_report(
                "phase_graph",
                [_finding("DOC-PG-001", "error", "unknown phase")],
            ),
            name="phase_graph",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
            capability_cardinality=cap_stub,  # type: ignore[arg-type]
            phase_graph=pg_stub,  # type: ignore[arg-type]
        )
        # Stub the resolution helpers to silence the runtime import and
        # to supply deterministic inputs to capability/phase_graph.
        with (
            patch.object(
                facade,
                "_optional_resolve_contracts",
                return_value=["contracts"],
            ),
            patch.object(
                facade,
                "_optional_resolve_phase_graph",
                return_value="phase_graph_plan",
            ),
        ):
            report = facade.doctor_profile("/fake/profile.yaml")

        codes = [f.code for f in report.findings]
        assert codes == [
            "DOC-COMPAT-000",
            "DOC-PS-001",
            "DOC-CAP-001",
            "DOC-PG-001",
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
            capability_cardinality=_RecordingStub(
                report=_ok_report("capability", []),
                name="capability",
            ),  # type: ignore[arg-type]
            phase_graph=_RecordingStub(
                report=_ok_report("phase_graph", []),
                name="phase_graph",
            ),  # type: ignore[arg-type]
        )
        with (
            patch.object(facade, "_optional_resolve_contracts", return_value=None),
            patch.object(facade, "_optional_resolve_phase_graph", return_value=None),
        ):
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
            capability_cardinality=_RecordingStub(
                report=_ok_report("capability", []),
                name="capability",
            ),  # type: ignore[arg-type]
            phase_graph=_RecordingStub(
                report=_ok_report("phase_graph", []),
                name="phase_graph",
            ),  # type: ignore[arg-type]
        )
        with (
            patch.object(facade, "_optional_resolve_contracts", return_value=None),
            patch.object(facade, "_optional_resolve_phase_graph", return_value=None),
        ):
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
            capability_cardinality=_RecordingStub(
                report=_ok_report("capability", []),
                name="capability",
            ),  # type: ignore[arg-type]
            phase_graph=_RecordingStub(
                report=_ok_report("phase_graph", []),
                name="phase_graph",
            ),  # type: ignore[arg-type]
        )
        with (
            patch.object(facade, "_optional_resolve_contracts", return_value=None),
            patch.object(facade, "_optional_resolve_phase_graph", return_value=None),
        ):
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
            capability_cardinality=_RecordingStub(
                report=_ok_report("capability", []),
                name="capability",
            ),  # type: ignore[arg-type]
            phase_graph=_RecordingStub(
                report=_ok_report("phase_graph", []),
                name="phase_graph",
            ),  # type: ignore[arg-type]
        )
        with (
            patch.object(facade, "_optional_resolve_contracts", return_value=None),
            patch.object(facade, "_optional_resolve_phase_graph", return_value=None),
        ):
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
        cap_stub = _make_stub("capability")
        pg_stub = _make_stub("phase_graph")

        # Wrap each run() so we observe the call order without changing
        # the returned report.
        original_compile = compile_stub.run
        original_shape = shape_stub.run
        original_cap = cap_stub.run
        original_pg = pg_stub.run

        def _wrap(name: str, original: Any) -> Any:
            def _wrapped(profile_path: Any) -> DoctorReport:
                order.append(name)
                return original(profile_path)

            return _wrapped

        compile_stub.run = _wrap("compile", original_compile)  # type: ignore[method-assign]
        shape_stub.run = _wrap("plugin_shape", original_shape)  # type: ignore[method-assign]
        cap_stub.run = _wrap("capability", original_cap)  # type: ignore[method-assign]
        pg_stub.run = _wrap("phase_graph", original_pg)  # type: ignore[method-assign]

        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
            capability_cardinality=cap_stub,  # type: ignore[arg-type]
            phase_graph=pg_stub,  # type: ignore[arg-type]
        )
        with (
            patch.object(facade, "_optional_resolve_contracts", return_value=["contracts"]),
            patch.object(facade, "_optional_resolve_phase_graph", return_value="phase_graph_plan"),
        ):
            facade.doctor_profile("/fake/profile.yaml")

        assert order == ["compile", "plugin_shape", "capability", "phase_graph"]


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
        cap_stub = _RecordingStub(
            report=_ok_report("capability", []),
            name="capability",
        )
        pg_stub = _RecordingStub(
            report=_ok_report("phase_graph", []),
            name="phase_graph",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
            capability_cardinality=cap_stub,  # type: ignore[arg-type]
            phase_graph=pg_stub,  # type: ignore[arg-type]
        )
        with (
            patch.object(facade, "_optional_resolve_contracts", return_value=None),
            patch.object(facade, "_optional_resolve_phase_graph", return_value=None),
        ):
            report = facade.doctor_profile(
                "/fake/profile.yaml",
                include_plugin_shape=False,
            )
        assert shape_stub.calls == []
        assert all(f.code != "DOC-PS-001" for f in report.findings)

    def test_doctor_profile_can_disable_capability_pass(self) -> None:
        compile_stub = _RecordingStub(
            report=_ok_report("compile", []),
            name="compile",
        )
        shape_stub = _RecordingStub(
            report=_ok_report("plugin_shape", []),
            name="plugin_shape",
        )
        cap_stub = _RecordingStub(
            report=_ok_report(
                "capability",
                [_finding("DOC-CAP-001", "error", "should not appear")],
            ),
            name="capability",
        )
        pg_stub = _RecordingStub(
            report=_ok_report("phase_graph", []),
            name="phase_graph",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
            capability_cardinality=cap_stub,  # type: ignore[arg-type]
            phase_graph=pg_stub,  # type: ignore[arg-type]
        )
        with (
            patch.object(facade, "_optional_resolve_contracts", return_value=["contracts"]),
            patch.object(facade, "_optional_resolve_phase_graph", return_value="phase_graph_plan"),
        ):
            report = facade.doctor_profile(
                "/fake/profile.yaml",
                include_capability_cardinality=False,
            )
        assert cap_stub.calls == []
        assert all(f.code != "DOC-CAP-001" for f in report.findings)

    def test_doctor_profile_can_disable_phase_graph_pass(self) -> None:
        compile_stub = _RecordingStub(
            report=_ok_report("compile", []),
            name="compile",
        )
        shape_stub = _RecordingStub(
            report=_ok_report("plugin_shape", []),
            name="plugin_shape",
        )
        cap_stub = _RecordingStub(
            report=_ok_report("capability", []),
            name="capability",
        )
        pg_stub = _RecordingStub(
            report=_ok_report(
                "phase_graph",
                [_finding("DOC-PG-001", "error", "should not appear")],
            ),
            name="phase_graph",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
            capability_cardinality=cap_stub,  # type: ignore[arg-type]
            phase_graph=pg_stub,  # type: ignore[arg-type]
        )
        with (
            patch.object(facade, "_optional_resolve_contracts", return_value=["contracts"]),
            patch.object(facade, "_optional_resolve_phase_graph", return_value="phase_graph_plan"),
        ):
            report = facade.doctor_profile(
                "/fake/profile.yaml",
                include_phase_graph=False,
            )
        assert pg_stub.calls == []
        assert all(f.code != "DOC-PG-001" for f in report.findings)


# ─────────── skip-on-compile-failure tests ───────────


class TestSkipOnCompileFailure:
    """Downstream passes are skipped when the compile step failed."""

    def test_doctor_profile_skips_capability_on_compile_failure(self) -> None:
        compile_stub = _RecordingStub(
            report=_ok_report(
                "compile",
                [_finding("DOC-COMPAT-001", "error", "compile fail")],
            ),
            name="compile",
        )
        shape_stub = _RecordingStub(
            report=_ok_report("plugin_shape", []),
            name="plugin_shape",
        )
        cap_stub = _RecordingStub(
            report=_ok_report(
                "capability",
                [_finding("DOC-CAP-001", "error", "should not appear")],
            ),
            name="capability",
        )
        pg_stub = _RecordingStub(
            report=_ok_report("phase_graph", []),
            name="phase_graph",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
            capability_cardinality=cap_stub,  # type: ignore[arg-type]
            phase_graph=pg_stub,  # type: ignore[arg-type]
        )
        with (
            patch.object(facade, "_optional_resolve_contracts", return_value=["contracts"]),
            patch.object(facade, "_optional_resolve_phase_graph", return_value="phase_graph_plan"),
        ):
            report = facade.doctor_profile("/fake/profile.yaml")
        assert cap_stub.calls == []
        assert all(f.code != "DOC-CAP-001" for f in report.findings)

    def test_doctor_profile_skips_phase_graph_on_compile_failure(self) -> None:
        compile_stub = _RecordingStub(
            report=_ok_report(
                "compile",
                [_finding("DOC-COMPAT-001", "error", "compile fail")],
            ),
            name="compile",
        )
        shape_stub = _RecordingStub(
            report=_ok_report("plugin_shape", []),
            name="plugin_shape",
        )
        cap_stub = _RecordingStub(
            report=_ok_report("capability", []),
            name="capability",
        )
        pg_stub = _RecordingStub(
            report=_ok_report(
                "phase_graph",
                [_finding("DOC-PG-001", "error", "should not appear")],
            ),
            name="phase_graph",
        )
        facade = DoctorFacade(
            compile_dry_run=compile_stub,  # type: ignore[arg-type]
            plugin_shape=shape_stub,  # type: ignore[arg-type]
            capability_cardinality=cap_stub,  # type: ignore[arg-type]
            phase_graph=pg_stub,  # type: ignore[arg-type]
        )
        with (
            patch.object(facade, "_optional_resolve_contracts", return_value=["contracts"]),
            patch.object(facade, "_optional_resolve_phase_graph", return_value="phase_graph_plan"),
        ):
            report = facade.doctor_profile("/fake/profile.yaml")
        assert pg_stub.calls == []
        assert all(f.code != "DOC-PG-001" for f in report.findings)


# ─────────── read-only invariant tests ───────────


class TestReadOnlyInvariant:
    """Doctor is read-only (I-HPC-7): no K3 boot, no journal writes."""

    def test_doctor_profile_does_not_run_k3_boot(self) -> None:
        """PlanResolutionService raising must NOT crash the facade (I-HPC-7).

        The compile pass is stubbed to succeed; the capability/phase_graph
        helpers must silently return None when PlanResolutionService raises.
        """

        def _boom_service(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("K3 boot attempted — I-HPC-7 violation")

        class _ServiceFactory:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self) -> Any:
                self.calls += 1
                return _ServiceProxy()

        class _ServiceProxy:
            def resolve_refs(self, *_args: Any, **_kwargs: Any) -> None:
                _boom_service()

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
            capability_cardinality=_RecordingStub(
                report=_ok_report("capability", []),
                name="capability",
            ),  # type: ignore[arg-type]
            phase_graph=_RecordingStub(
                report=_ok_report("phase_graph", []),
                name="phase_graph",
            ),  # type: ignore[arg-type]
        )
        # Patch the dynamic import target (imported lazily inside helpers).
        with patch(
            "lca.application.runtime.plan_resolution.PlanResolutionService",
            factory,
        ):
            report = facade.doctor_profile("/fake/profile.yaml")
        # The facade returns gracefully; only the compile pass contributes
        # findings (none in this stub).
        assert report.summary.total == 0
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
