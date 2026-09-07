"""Behavioral tests for the PluginShapeDoctor pass (PR-0199-P2-04).

Per ADR-0199 §5.1 + §5.2 the doctor is a compile-pipeline projection
that wraps the existing ``scripts/check_plugin_shape.py`` rather than
re-implementing its rules. These tests assert:
  * subprocess invocation (the script is the SSOT for audit dimensions),
  * stable DOC-PS-* code mapping per dimension (kind),
  * I-HPC-7 invariants (no journal/session imports, deterministic),
  * never raises for clean tree, surfaces DOC-PS-901 when script missing.
"""

from __future__ import annotations

import json
import re
import stat
from pathlib import Path
from typing import Any

import pytest

from lca.harness.diagnostics.doctor.plugin_shape import (
    _CODE_BY_KIND,
    PluginShapeDoctor,
)

# Stable machine-code regex copied verbatim from
# lca.contracts.diagnostics.doctor (DOC-<DOMAIN>-<NNN>).
_CODE_RE = re.compile(r"^DOC-[A-Z]{2,6}-\d{3,}$")


# ─────────── helpers ───────────


def _write_stub_script(
    path: Path,
    *,
    payload: dict[str, Any] | None = None,
    exit_code: int = 0,
    stderr: str = "",
    extra_stdout: str = "",
) -> Path:
    """Write a small Python script that prints the JSON payload + exits.

    The stub intentionally mimics scripts/check_plugin_shape.py's output
    shape (root / by_kind / violations[*].kind/id/file/line/detail).
    """
    payload_json = json.dumps(payload if payload is not None else {"violations": []})
    body = (
        "import json, sys\n"
        f"sys.stderr.write({stderr!r})\n"
        f"print({extra_stdout!r})\n"
        f"print({payload_json!r})\n"
        f"sys.exit({exit_code})\n"
    )
    path.write_text(body, encoding="utf-8")
    # Make executable (some sandbox setups require it).
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _stub_payload_for_kind(
    kind: str,
    *,
    plugin_id: str = "lca.plugins.example.example",
    file_path: str = "lca/plugins/example/example.py",
    line: int = 10,
    detail: str | None = None,
) -> dict[str, Any]:
    """Build a single-violation payload matching check_plugin_shape.py shape."""
    return {
        "root": "/repo/lca/plugins",
        "total_plugins": 1,
        "by_kind": {kind: 1},
        "baseline": {kind: 0},
        "regression": {kind: 1},
        "violations": [
            {
                "kind": kind,
                "id": plugin_id,
                "file": file_path,
                "line": line,
                "detail": detail or f"stub violation for kind={kind}",
            }
        ],
    }


# ─────────── TestSubject ───────────


class TestSubjectAndDefaults:
    """DoctorReport.subject is fixed to 'plugin_shape' (no profile path)."""

    def test_run_returns_report_subject_plugin_shape(self, tmp_path: Path) -> None:
        script = _write_stub_script(tmp_path / "stub.py", payload={"violations": []})
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        assert report.subject == "plugin_shape"

    def test_run_profile_path_argument_is_ignored(self, tmp_path: Path) -> None:
        """profile_path is accepted for facade parity but unused."""
        script = _write_stub_script(tmp_path / "stub.py", payload={"violations": []})
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        # Passing a profile_path must not change behavior or raise.
        report = doctor.run("/some/profile.yaml")
        assert report.subject == "plugin_shape"
        assert report.findings == ()

    def test_run_uses_invoked_script_path_when_set_explicitly(self, tmp_path: Path) -> None:
        script = _write_stub_script(
            tmp_path / "stub.py",
            payload=_stub_payload_for_kind("missing_effects", plugin_id="explicit.id"),
        )
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        assert len(report.findings) == 1
        assert report.findings[0].code == "DOC-PS-001"
        assert report.findings[0].plugin_id == "explicit.id"


# ─────────── MissingScript ───────────


class TestMissingScript:
    """When the wrapped script is missing, surface DOC-PS-901."""

    def test_run_handles_missing_script_with_doc_ps_901_finding(self, tmp_path: Path) -> None:
        doctor = PluginShapeDoctor(repo_root=tmp_path)
        report = doctor.run()
        assert report.summary.errors == 1
        finding = report.findings[0]
        assert finding.code == "DOC-PS-901"
        assert finding.severity == "error"
        assert finding.owner == "ADR-0199"
        assert "check_plugin_shape.py" in finding.message

    def test_run_default_script_path_resolves_under_repo_root(self, tmp_path: Path) -> None:
        """__init__ default constructs <repo_root>/scripts/check_plugin_shape.py."""
        # No script created under tmp_path/scripts/ → must report DOC-PS-901.
        doctor = PluginShapeDoctor(repo_root=tmp_path)
        report = doctor.run()
        assert any(f.code == "DOC-PS-901" for f in report.findings)


# ─────────── CodeMapping ───────────


class TestCodeMapping:
    """Every check_plugin_shape.py kind maps to a stable DOC-PS-NNN code."""

    @pytest.mark.parametrize(
        "kind,expected_code",
        [
            ("missing_effects", "DOC-PS-001"),
            ("dual_form_residue", "DOC-PS-002"),
            ("duplicate_id", "DOC-PS-003"),
            ("plugin_location", "DOC-PS-004"),
            ("orphan_plugin", "DOC-PS-005"),
            ("dead_bundle_ref", "DOC-PS-006"),
            ("plugin_in_init", "DOC-PS-007"),
        ],
    )
    def test_run_converts_violation_dimensions_to_codes(
        self,
        tmp_path: Path,
        kind: str,
        expected_code: str,
    ) -> None:
        script = _write_stub_script(tmp_path / "stub.py", payload=_stub_payload_for_kind(kind))
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        assert len(report.findings) == 1
        finding = report.findings[0]
        assert finding.code == expected_code
        assert _CODE_RE.match(finding.code)
        assert finding.owner == "ADR-0199"
        assert finding.message  # non-empty
        assert finding.remediation  # non-empty (DoctorFinding.__post_init__)

    def test_dimension_to_code_mapping_is_complete(self) -> None:
        """Every key in _CODE_BY_KIND maps to a DOC-PS-NNN code."""
        assert len(_CODE_BY_KIND) >= 7, (
            "Expected at least 7 dimension codes (Phase A + PR-1 + AGENTS §5)."
        )
        for kind, code in _CODE_BY_KIND.items():
            assert _CODE_RE.match(code), f"{kind!r} → {code!r} not DOC-XX-NNN"
            # Each code starts with DOC-PS- (this doctor's domain).
            assert code.startswith("DOC-PS-"), (
                f"PluginShapeDoctor must use DOC-PS-* prefix; got {code!r}"
            )


# ─────────── SeverityBands ───────────


class TestSeverityBands:
    """Severity is determined by the violation kind."""

    def test_run_uses_warning_severity_for_orphan_plugins(self, tmp_path: Path) -> None:
        script = _write_stub_script(
            tmp_path / "stub.py", payload=_stub_payload_for_kind("orphan_plugin")
        )
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        assert report.findings[0].severity == "warning"
        assert report.summary.warnings == 1

    def test_run_uses_error_severity_for_missing_effects(self, tmp_path: Path) -> None:
        script = _write_stub_script(
            tmp_path / "stub.py", payload=_stub_payload_for_kind("missing_effects")
        )
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        assert report.findings[0].severity == "error"
        assert report.summary.errors == 1

    def test_run_warning_severity_for_dead_bundle_ref(self, tmp_path: Path) -> None:
        script = _write_stub_script(
            tmp_path / "stub.py", payload=_stub_payload_for_kind("dead_bundle_ref")
        )
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        assert report.findings[0].severity == "warning"


# ─────────── PluginIdPropagation ───────────


class TestPluginIdPropagation:
    """Violation plugin_id must carry into DoctorFinding.plugin_id."""

    def test_run_carries_plugin_id_in_finding(self, tmp_path: Path) -> None:
        script = _write_stub_script(
            tmp_path / "stub.py",
            payload=_stub_payload_for_kind("missing_effects", plugin_id="lca.plugins.foo.bar"),
        )
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        assert report.findings[0].plugin_id == "lca.plugins.foo.bar"


# ─────────── EmptyAndSubprocessFailure ───────────


class TestEmptyAndSubprocessFailure:
    """Clean tree → empty findings; unexpected subprocess exit → RuntimeError."""

    def test_run_empty_when_no_violations(self, tmp_path: Path) -> None:
        script = _write_stub_script(tmp_path / "stub.py", payload={"violations": []})
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        assert report.summary.total == 0
        assert report.findings == ()
        assert report.has_errors() is False

    def test_run_never_raises_for_clean_tree(self, tmp_path: Path) -> None:
        script = _write_stub_script(
            tmp_path / "stub.py",
            payload={"root": "/x", "violations": []},
        )
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        # Must not raise even though payload has no total_plugins key.
        report = doctor.run()
        assert report.summary.errors == 0

    def test_run_subprocess_failure_with_stderr_raises_runtime_error(self, tmp_path: Path) -> None:
        script = _write_stub_script(
            tmp_path / "stub.py",
            payload=None,
            exit_code=2,
            stderr="boom: unrecoverable scan error",
        )
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        with pytest.raises(RuntimeError) as excinfo:
            doctor.run()
        assert "exit 2" in str(excinfo.value)
        assert "boom: unrecoverable" in str(excinfo.value)

    def test_run_handles_non_json_stdout_as_empty(self, tmp_path: Path) -> None:
        """Script printing non-JSON before/during → no parse error, empty."""
        script = _write_stub_script(
            tmp_path / "stub.py",
            payload=None,
            exit_code=0,
            extra_stdout="INFO: starting scan...",
        )
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        assert report.findings == ()

    def test_run_handles_multiple_violations(self, tmp_path: Path) -> None:
        payload = {
            "violations": [
                {
                    "kind": "missing_effects",
                    "id": "lca.plugins.a.a",
                    "file": "lca/plugins/a/a.py",
                    "line": 1,
                    "detail": "missing effects",
                },
                {
                    "kind": "duplicate_id",
                    "id": "lca.plugins.b.b",
                    "file": "lca/plugins/b/b.py",
                    "line": 5,
                    "detail": "duplicate id",
                },
            ]
        }
        script = _write_stub_script(tmp_path / "stub.py", payload=payload)
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        codes = sorted(f.code for f in report.findings)
        assert codes == ["DOC-PS-001", "DOC-PS-003"]
        assert report.summary.errors == 2

    def test_run_handles_unknown_kind_as_info(self, tmp_path: Path) -> None:
        """Unknown kinds fall back to DOC-PS-999 + info severity."""
        payload = {
            "violations": [
                {
                    "kind": "future_kind_not_in_mapping",
                    "id": "x",
                    "file": "f.py",
                    "line": 1,
                    "detail": "future",
                }
            ]
        }
        script = _write_stub_script(tmp_path / "stub.py", payload=payload)
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        finding = report.findings[0]
        assert finding.code == "DOC-PS-999"
        assert finding.severity == "info"

    def test_run_includes_file_and_line_in_message(self, tmp_path: Path) -> None:
        payload = _stub_payload_for_kind(
            "missing_effects",
            file_path="lca/plugins/example/example.py",
            line=42,
        )
        script = _write_stub_script(tmp_path / "stub.py", payload=payload)
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        report = doctor.run()
        message = report.findings[0].message
        assert "lca/plugins/example/example.py" in message
        assert "42" in message


# ─────────── ArchitecturalInvariants ───────────


class TestArchitecturalInvariants:
    """Per I-HPC-7 + I-HPC-9: no K3 boot, no journal writes, no global registry."""

    def test_run_does_not_import_session_or_journal(self) -> None:
        """Module must not import lca.session / lca.journal backends."""
        import lca.harness.diagnostics.doctor.plugin_shape as mod

        source_file = Path(mod.__file__)
        assert source_file.is_file()
        text = source_file.read_text(encoding="utf-8")
        # AST scan to avoid catching docstring/comment matches.
        import ast as _ast

        tree = _ast.parse(text)
        imported: list[str] = []
        for node in _ast.walk(tree):
            if isinstance(node, _ast.ImportFrom):
                mod_name = node.module or ""
                if mod_name.startswith("lca.session") or mod_name.startswith("lca.journal"):
                    imported.append(mod_name)
            elif isinstance(node, _ast.Import):
                for alias in node.names:
                    if alias.name.startswith("lca.session") or alias.name.startswith("lca.journal"):
                        imported.append(alias.name)
        assert imported == [], (
            f"PluginShapeDoctor must NOT import session/journal (I-HPC-7); got {imported!r}"
        )

    def test_run_does_not_call_session_or_journal(self) -> None:
        """No 'Session.' / 'Journal.' / 'append(' references in module source."""
        import lca.harness.diagnostics.doctor.plugin_shape as mod

        text = Path(mod.__file__).read_text(encoding="utf-8")
        # Loose check: ensure no obvious forbidden identifiers at module level.
        # (We don't try to be clever; the structural scan above is the
        # authoritative check.)
        for forbidden in ("Session.append", "Journal.append"):
            assert forbidden not in text, (
                f"PluginShapeDoctor source must not reference {forbidden!r}"
            )


# ─────────── Determinism ───────────


class TestDeterminism:
    """C8: same wrapped script → same findings across calls."""

    def test_same_input_same_output(self, tmp_path: Path) -> None:
        payload = _stub_payload_for_kind("missing_effects", plugin_id="x.y")
        script = _write_stub_script(tmp_path / "stub.py", payload=payload)
        doctor = PluginShapeDoctor(repo_root=tmp_path, check_script=script)
        a = doctor.run()
        b = doctor.run()
        assert a.to_jsonable() == b.to_jsonable()
