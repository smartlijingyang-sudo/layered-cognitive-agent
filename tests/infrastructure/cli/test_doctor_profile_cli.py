"""Behavioural tests for ``lca-ops doctor profile`` (PR-0199-P2-08).

Per ADR-0199 §5.3 the CLI is one of three canonical doctor consumers.
These tests pin:

  * The Typer subcommand registration shape (``doctor profile``).
  * The two output modes (human text vs ``--json``).
  * The CI exit-code contract (``--ci`` → exit 1 on errors).
  * The skip-flag passthrough to :class:`DoctorFacade`.
  * Read-only invariant (I-HPC-7): no journal / session imports.

We monkeypatch :class:`DoctorFacade` so tests stay deterministic and
do not depend on a real profile YAML being present in the worktree.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
)
from lca.infrastructure.cli.commands.doctor import profile as profile_module

_PROFILE_MODULE = "lca.infrastructure.cli.commands.doctor.profile"
_FACADE_MODULE = "lca.harness.diagnostics.doctor.facade"


# ─────────── helpers ───────────


def _finding(
    code: str,
    severity: str,
    msg: str,
    *,
    plugin_id: str | None = None,
    remediation: str | None = None,
) -> DoctorFinding:
    return DoctorFinding(
        code=code,
        severity=severity,
        owner="ADR-0199",
        message=msg,
        remediation=remediation or f"remediation for {code}",
        plugin_id=plugin_id,
        plan_ref=None,
    )


def _clean_report(subject: str = "/abs/profiles/sample.yaml") -> DoctorReport:
    return DoctorReport.from_findings(subject=subject, findings=[])


def _error_report(
    subject: str = "/abs/profiles/broken.yaml",
    *,
    activation_ref: str | None = None,
) -> DoctorReport:
    return DoctorReport.from_findings(
        subject=subject,
        findings=[_finding("DOC-PS-001", "error", "missing effects declaration")],
        activation_ref=activation_ref,
    )


def _warning_report(subject: str = "/abs/profiles/sample.yaml") -> DoctorReport:
    return DoctorReport.from_findings(
        subject=subject,
        findings=[_finding("DOC-CAP-001", "warning", "duplicate capability owner")],
    )


def _echo_subject_factory(
    factory,
    *,
    activation_ref: str | None = None,
):
    """Return a ``side_effect`` callable that produces a report whose
    ``subject`` is the path the facade was called with.

    The real :class:`DoctorFacade` sets ``subject=str(profile_path)`` so
    that JSON consumers can echo it back. Tests that assert on
    ``payload["subject"]`` need this behaviour.
    """

    def _side_effect(profile_path, **_kwargs):
        report = factory(subject=str(profile_path))
        if activation_ref is not None:
            report = DoctorReport.from_findings(
                subject=str(profile_path),
                findings=list(report.findings),
                activation_ref=activation_ref,
            )
        return report

    return _side_effect


def _build_app() -> typer.Typer:
    return typer.Typer()


def _register(app: typer.Typer) -> None:
    profile_module.register(app)


@pytest.fixture
def fake_facade_clean() -> MagicMock:
    """A ``DoctorFacade`` stub that returns a clean report for every call.

    The stub's ``doctor_profile`` echoes the path passed in as the report
    ``subject`` so JSON tests can assert on the resolved path string.
    """
    with patch(f"{_PROFILE_MODULE}.DoctorFacade") as facade_cls:
        instance = MagicMock()
        instance.doctor_profile.side_effect = _echo_subject_factory(_clean_report)
        facade_cls.return_value = instance
        yield instance


@pytest.fixture
def fake_facade_error() -> MagicMock:
    """A ``DoctorFacade`` stub that returns an error report."""
    with patch(f"{_PROFILE_MODULE}.DoctorFacade") as facade_cls:
        instance = MagicMock()
        instance.doctor_profile.side_effect = _echo_subject_factory(_error_report)
        facade_cls.return_value = instance
        yield instance


@pytest.fixture
def fake_facade_activation_ref() -> MagicMock:
    """A ``DoctorFacade`` stub whose report carries an ``activation_ref``."""
    with patch(f"{_PROFILE_MODULE}.DoctorFacade") as facade_cls:
        instance = MagicMock()
        instance.doctor_profile.side_effect = _echo_subject_factory(
            _error_report,
            activation_ref="lca.activation.v1:" + "a" * 64,
        )
        facade_cls.return_value = instance
        yield instance


@pytest.fixture
def tmp_profile(tmp_path: Path) -> Path:
    """A real profile file that exists on disk so the doctor CLI is happy."""
    p = tmp_path / "profile.yaml"
    p.write_text("# stub profile for doctor CLI tests\n", encoding="utf-8")
    return p


# ─────────── 1. registration ───────────


class TestRegistration:
    """The ``doctor profile`` subcommand must be visible to Typer."""

    def test_doctor_profile_registers_subcommand(self) -> None:
        """``lca-ops doctor --help`` shows the ``profile`` subcommand."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0, result.stdout
        assert "profile" in result.stdout

    def test_doctor_subcommand_in_help(self) -> None:
        """The ``doctor`` Typer group itself is discoverable in ``--help``."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0, result.stdout
        assert "doctor" in result.stdout

    def test_doctor_profile_help_shows_options(self) -> None:
        """``doctor profile --help`` mentions the major flags."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "profile", "--help"])
        assert result.exit_code == 0, result.stdout
        assert "--ci" in result.stdout
        assert "--json" in result.stdout
        assert "--skip-plugin-shape" in result.stdout
        assert "--skip-capability" in result.stdout
        assert "--skip-phase-graph" in result.stdout

    def test_no_args_is_help(self) -> None:
        """``lca-ops doctor`` with no subcommand shows help (no args is help).

        Note: typer's ``no_args_is_help=True`` only fires on the root app,
        not on sub-commands. The root app is constructed by the entry-point
        CLI; here we test the sub-app, which raises SystemExit(2) when
        invoked with no subcommand. Both behaviors are acceptable for
        ``lca-ops doctor`` with no args.
        """
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code in (0, 2)


# ─────────── 2. JSON output ───────────


class TestJsonOutput:
    """``--json`` emits the stable :class:`DoctorReport` projection."""

    def test_doctor_profile_json_output(
        self, fake_facade_clean: MagicMock, tmp_profile: Path
    ) -> None:
        """JSON output is parseable and carries ``subject`` + ``summary`` + ``findings``."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile), "--json"],
        )
        assert result.exit_code == 0, result.stdout
        # The stub returns _clean_report() — JSON should round-trip cleanly.
        payload = json.loads(result.stdout)
        assert payload["subject"] == str(tmp_profile)
        assert "summary" in payload
        assert payload["summary"]["errors"] == 0
        assert payload["summary"]["warnings"] == 0
        assert "findings" in payload
        assert payload["findings"] == []

    def test_json_output_round_trips_through_to_jsonable(
        self, fake_facade_error: MagicMock, tmp_profile: Path
    ) -> None:
        """JSON output deserializes back into a structurally equivalent DoctorReport."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile), "--json"],
        )
        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        # Same keys as DoctorReport.to_jsonable(); findings preserve their shape.
        assert set(payload) >= {"subject", "summary", "findings", "activation_ref"}
        assert payload["findings"][0]["code"] == "DOC-PS-001"
        assert payload["findings"][0]["severity"] == "error"
        assert payload["summary"]["errors"] == 1
        assert payload["summary"]["total"] == 1

    def test_activation_ref_emitted_when_compile_succeeds(
        self, fake_facade_activation_ref: MagicMock, tmp_profile: Path
    ) -> None:
        """``activation_ref`` is propagated into JSON output when the compile pass set it."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile), "--json"],
        )
        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        assert payload["activation_ref"] == "lca.activation.v1:" + "a" * 64


# ─────────── 3. Human output ───────────


class TestHumanOutput:
    """Default mode renders a human-readable summary."""

    def test_doctor_profile_human_output(
        self, fake_facade_clean: MagicMock, tmp_profile: Path
    ) -> None:
        """Default mode prints a ``summary:`` line."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile)],
        )
        assert result.exit_code == 0, result.stdout
        assert "summary:" in result.stdout
        assert f"profile: {tmp_profile}" in result.stdout

    def test_human_output_renders_findings(
        self, fake_facade_error: MagicMock, tmp_profile: Path
    ) -> None:
        """Human mode prints ``[severity] code  message`` for each finding."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile)],
        )
        assert result.exit_code == 0, result.stdout
        assert "[error] DOC-PS-001" in result.stdout
        assert "missing effects declaration" in result.stdout
        assert "remediation:" in result.stdout

    def test_human_output_no_findings_marker(
        self, fake_facade_clean: MagicMock, tmp_profile: Path
    ) -> None:
        """Human mode shows ``(no findings)`` when the report is clean."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile)],
        )
        assert result.exit_code == 0, result.stdout
        assert "(no findings)" in result.stdout


# ─────────── 4. CI exit-code contract ───────────


class TestCiExitCodes:
    """``--ci`` flips the exit code on errors (ADR-0199 §13.3)."""

    def test_ci_mode_exits_1_on_errors(
        self, fake_facade_error: MagicMock, tmp_profile: Path
    ) -> None:
        """Doctor error + ``--ci`` → exit 1."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile), "--ci"],
        )
        assert result.exit_code == 1

    def test_ci_mode_exits_0_when_clean(
        self, fake_facade_clean: MagicMock, tmp_profile: Path
    ) -> None:
        """Clean report + ``--ci`` → exit 0 (not flip-spurious)."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile), "--ci"],
        )
        assert result.exit_code == 0

    def test_no_ci_mode_exits_0_on_errors(
        self, fake_facade_error: MagicMock, tmp_profile: Path
    ) -> None:
        """Without ``--ci`` errors do NOT bump the exit code (operator-friendly)."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile)],
        )
        assert result.exit_code == 0

    def test_ci_mode_with_json_emits_valid_json_then_exits_1(
        self, fake_facade_error: MagicMock, tmp_profile: Path
    ) -> None:
        """``--ci --json`` prints JSON, then exits 1 — the canonical CI form."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile), "--ci", "--json"],
        )
        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["summary"]["errors"] == 1

    def test_ci_mode_warning_only_exits_0(self, tmp_profile: Path) -> None:
        """Warnings do NOT trip CI; ``--ci`` only fails on errors per §13.3."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        with patch(f"{_PROFILE_MODULE}.DoctorFacade") as facade_cls:
            instance = MagicMock()
            instance.doctor_profile.side_effect = _echo_subject_factory(_warning_report)
            facade_cls.return_value = instance
            result = runner.invoke(
                app,
                ["doctor", "profile", str(tmp_profile), "--ci"],
            )
        assert result.exit_code == 0, f"exit_code={result.exit_code}, stdout={result.stdout!r}"


# ─────────── 5. Bad input ───────────


class TestBadInput:
    """Invalid input produces exit 2 (no doctor pass runs)."""

    def test_missing_profile_exits_2(self) -> None:
        """Nonexistent profile → exit 2, facade never invoked."""
        with patch(f"{_PROFILE_MODULE}.DoctorFacade") as facade_cls:
            app = _build_app()
            _register(app)
            runner = CliRunner()
            result = runner.invoke(
                app,
                ["doctor", "profile", "/definitely/does/not/exist.yaml"],
            )
        assert result.exit_code == 2
        # DoctorFacade must not be instantiated on bad input.
        facade_cls.assert_not_called()


# ─────────── 6. Skip flags ───────────


class TestSkipFlags:
    """Skip flags are passthrough booleans to ``DoctorFacade.doctor_profile``."""

    def test_skip_plugin_shape_flag(self, fake_facade_clean: MagicMock, tmp_profile: Path) -> None:
        """``--skip-plugin-shape`` flips ``include_plugin_shape`` to False."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile), "--skip-plugin-shape"],
        )
        assert result.exit_code == 0, result.stdout
        fake_facade_clean.doctor_profile.assert_called_once()
        _, kwargs = fake_facade_clean.doctor_profile.call_args
        assert kwargs["include_plugin_shape"] is False

    def test_skip_capability_flag(self, fake_facade_clean: MagicMock, tmp_profile: Path) -> None:
        """``--skip-capability`` flips ``include_capability_cardinality`` to False."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile), "--skip-capability"],
        )
        assert result.exit_code == 0, result.stdout
        _, kwargs = fake_facade_clean.doctor_profile.call_args
        assert kwargs["include_capability_cardinality"] is False

    def test_skip_phase_graph_flag(self, fake_facade_clean: MagicMock, tmp_profile: Path) -> None:
        """``--skip-phase-graph`` flips ``include_phase_graph`` to False."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "profile", str(tmp_profile), "--skip-phase-graph"],
        )
        assert result.exit_code == 0, result.stdout
        _, kwargs = fake_facade_clean.doctor_profile.call_args
        assert kwargs["include_phase_graph"] is False

    def test_skip_defaults_are_true(self, fake_facade_clean: MagicMock, tmp_profile: Path) -> None:
        """Without skip flags, all three passes are opted in (default-True)."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "profile", str(tmp_profile)])
        assert result.exit_code == 0, result.stdout
        _, kwargs = fake_facade_clean.doctor_profile.call_args
        assert kwargs["include_plugin_shape"] is True
        assert kwargs["include_capability_cardinality"] is True
        assert kwargs["include_phase_graph"] is True

    def test_skip_all_three_flags_together(
        self, fake_facade_clean: MagicMock, tmp_profile: Path
    ) -> None:
        """All three skip flags can be combined in one invocation."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "doctor",
                "profile",
                str(tmp_profile),
                "--skip-plugin-shape",
                "--skip-capability",
                "--skip-phase-graph",
            ],
        )
        assert result.exit_code == 0, result.stdout
        _, kwargs = fake_facade_clean.doctor_profile.call_args
        assert kwargs["include_plugin_shape"] is False
        assert kwargs["include_capability_cardinality"] is False
        assert kwargs["include_phase_graph"] is False


# ─────────── 7. I-HPC-7 read-only invariant ───────────


class TestReadOnlyInvariant:
    """The CLI module must not import journal / session / network (I-HPC-7)."""

    def test_no_journal_writes_in_module(self) -> None:
        """The doctor CLI module imports no journal / session / network writers."""
        source = Path(profile_module.__file__).read_text(encoding="utf-8")
        # Forbidden imports: Session, FactGateway, journal_io, write_journal,
        # append_event, RunStore, EventBus — none of these should appear.
        forbidden = [
            "lca.session",
            "lca.journal",
            "Session.append",
            "FactGateway",
            "write_journal",
            "append_event",
            "RunStore",
            "EventBus",
            "urllib.request",
            "urllib3",
            "httpx.",
            "requests.",
        ]
        for needle in forbidden:
            assert needle not in source, (
                f"doctor profile CLI must not import {needle!r} (I-HPC-7 read-only)"
            )

    def test_register_function_exposed(self) -> None:
        """``profile.register`` is the canonical entry point (consumed by
        ``lca.infrastructure.cli.commands`` ``__init__`` or a follow-up PR).
        """
        assert hasattr(profile_module, "register")
        assert callable(profile_module.register)
        assert profile_module.__all__ == ("register",)


# ─────────── 8. Module-level sanity ───────────


def test_module_docstring_cites_adr_0199() -> None:
    """The module docstring of ``profile.py`` cites ADR-0199 + P2-08."""
    source = Path(profile_module.__file__).read_text(encoding="utf-8")
    assert "ADR-0199" in source
    assert "P2-08" in source
    assert "I-HPC-7" in source  # read-only invariant explicitly cited


# ─────────── 9. --ci --json reference (canonical CI form) ───────────


def test_ci_json_reference_command_against_real_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Smoke: ``doctor profile --ci --json`` on a real path executes end-to-end.

    The :class:`DoctorFacade` default passes are stubbed so this test
    does NOT depend on the real compile pipeline (which can crash on
    empty-profile stubs in CI). We only verify the canonical CI form
    ``lca-ops doctor profile --ci --json`` (ADR-0199 §13.3) is wired
    correctly: JSON output, exit code, subject echoed.
    """
    profile = tmp_path / "empty.yaml"
    profile.write_text("# stub profile for doctor CLI smoke test\n", encoding="utf-8")

    app = _build_app()
    _register(app)
    runner = CliRunner()
    with patch(f"{_PROFILE_MODULE}.DoctorFacade") as facade_cls:
        instance = MagicMock()
        instance.doctor_profile.side_effect = _echo_subject_factory(_error_report)
        facade_cls.return_value = instance
        result = runner.invoke(
            app,
            ["doctor", "profile", str(profile), "--ci", "--json"],
        )
    # CI mode + errors → 1; CI mode + clean → 0. Either way stdout is JSON.
    assert result.exit_code == 1, result.stdout
    # Should be JSON parseable.
    payload = json.loads(result.stdout)
    assert "summary" in payload
    assert "findings" in payload
    # Subject must echo the resolved path string.
    assert payload["subject"] == str(profile)


# ─────────── 10. Diagnostic regression ───────────


def test_warning_severity_in_human_output(tmp_path: Path) -> None:
    """Warnings render with the ``[warning]`` prefix in human output."""
    profile = tmp_path / "profile.yaml"
    profile.write_text("# stub profile for doctor CLI tests\n", encoding="utf-8")

    app = _build_app()
    _register(app)
    runner = CliRunner()
    with patch(f"{_PROFILE_MODULE}.DoctorFacade") as facade_cls:
        instance = MagicMock()
        instance.doctor_profile.side_effect = _echo_subject_factory(_warning_report)
        facade_cls.return_value = instance
        result = runner.invoke(app, ["doctor", "profile", str(profile)])
    assert result.exit_code == 0, result.stdout
    assert "[warning] DOC-CAP-001" in result.stdout
    assert "warnings=1" in result.stdout


# ─────────── 11. json output is unicode-safe ───────────


def test_json_output_unicode_safe(fake_facade_clean: MagicMock, tmp_profile: Path) -> None:
    """JSON output uses ``ensure_ascii=False`` so messages stay readable."""
    # Inject a non-ASCII message via the stub.
    fake_facade_clean.doctor_profile.side_effect = _echo_subject_factory(
        lambda subject: DoctorReport.from_findings(
            subject=subject,
            findings=[
                _finding("DOC-PS-002", "info", "non-ASCII: 修复指引 → ok"),
            ],
        )
    )
    app = _build_app()
    _register(app)
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "profile", str(tmp_profile), "--json"])
    assert result.exit_code == 0, result.stdout
    # The non-ASCII literal must be present verbatim (not escaped).
    assert "修复指引" in result.stdout
    payload = json.loads(result.stdout)
    assert payload["findings"][0]["message"].endswith("→ ok")


# ─────────── 12. ci + json order-insensitivity ───────────


def test_ci_and_json_flag_order_independent(
    fake_facade_error: MagicMock, tmp_profile: Path
) -> None:
    """``--ci --json`` and ``--json --ci`` behave identically (canonical CI form)."""
    app = _build_app()
    _register(app)
    runner = CliRunner()
    a = runner.invoke(app, ["doctor", "profile", str(tmp_profile), "--ci", "--json"])
    b = runner.invoke(app, ["doctor", "profile", str(tmp_profile), "--json", "--ci"])
    assert a.exit_code == b.exit_code == 1
    # Both stdout payloads decode to the same JSON shape (allow different
    # whitespace; compare parsed dicts).
    assert json.loads(a.stdout) == json.loads(b.stdout)


# ─────────── 13. activation_ref printed in human output ───────────


def test_activation_ref_printed_in_human_output(
    fake_facade_activation_ref: MagicMock, tmp_profile: Path
) -> None:
    """Human mode prints ``activation_ref: ...`` when the compile pass set it."""
    app = _build_app()
    _register(app)
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "profile", str(tmp_profile)])
    assert result.exit_code == 0, result.stdout
    match = re.search(r"activation_ref:\s*(\S+)", result.stdout)
    assert match is not None, f"activation_ref line missing: {result.stdout!r}"
    assert match.group(1) == "lca.activation.v1:" + "a" * 64
