"""Behavioural tests for ``lca-ops doctor plugin`` (RA-067).

Per ADR-0199 §5.1 / P2-09 the single-plugin doctor audits ONE plugin
module via pure AST (no import, no boot). RA-067 wires it as
``lca-ops doctor plugin <path>`` so the tested module has a real
consumer. These tests pin:

  * The Typer subcommand registration shape (``doctor plugin``).
  * The two output modes (human text vs ``--json``).
  * The CI exit-code contract (``--ci`` → exit 1 on errors).
  * Bad input → exit 2.
  * Read-only invariant (I-HPC-7): the CLI module imports no
    journal / session / network writers.

Unlike the ``doctor profile`` CLI tests, these drive the REAL
:class:`SinglePluginDoctor` end-to-end — it is pure AST analysis,
deterministic, and needs no stubbing.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from typer.testing import CliRunner

from lca.infrastructure.cli.commands.doctor import profile as profile_module

_CLEAN_PLUGIN = '''"""A well-formed plugin for doctor CLI tests."""

from lca.harness.plugin_api import plugin


@plugin(id="test-clean-plugin", effects=("journal.read",))
async def setup(ctx, config):
    pass
'''

_NO_DECORATOR = '''"""A module with no @plugin decorator."""

VALUE = 42
'''

_SYNTAX_ERROR = "def broken(:\n"


def _build_app() -> typer.Typer:
    return typer.Typer()


def _register(app: typer.Typer) -> None:
    profile_module.register(app)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ─────────── 1. registration ───────────


class TestRegistration:
    def test_doctor_plugin_registers_subcommand(self) -> None:
        """``lca-ops doctor --help`` shows the ``plugin`` subcommand."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0, result.stdout
        assert "plugin" in result.stdout

    def test_doctor_plugin_help_shows_options(self) -> None:
        """``doctor plugin --help`` mentions the major flags."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "plugin", "--help"])
        assert result.exit_code == 0, result.stdout
        assert "--ci" in result.stdout
        assert "--json" in result.stdout

    def test_profile_subcommand_still_registered(self) -> None:
        """Wiring ``plugin`` must not disturb the existing ``profile`` command."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0, result.stdout
        assert "profile" in result.stdout


# ─────────── 2. JSON output ───────────


class TestJsonOutput:
    def test_json_output_clean_plugin(self, tmp_path: Path) -> None:
        """A well-formed plugin yields a parseable JSON report with zero errors."""
        plugin = _write(tmp_path, "clean_plugin.py", _CLEAN_PLUGIN)
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "plugin", str(plugin), "--json"])
        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        assert payload["subject"] == str(plugin)
        assert "summary" in payload
        assert payload["summary"]["errors"] == 0
        assert "findings" in payload

    def test_json_output_reports_syntax_error(self, tmp_path: Path) -> None:
        """A syntax-broken file surfaces DOC-PS-902 in JSON."""
        plugin = _write(tmp_path, "broken.py", _SYNTAX_ERROR)
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "plugin", str(plugin), "--json"])
        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        assert payload["summary"]["errors"] == 1
        assert payload["findings"][0]["code"] == "DOC-PS-902"


# ─────────── 3. Human output ───────────


class TestHumanOutput:
    def test_human_output_labels_plugin_subject(self, tmp_path: Path) -> None:
        """Human mode prints ``plugin: <path>`` (not the profile label)."""
        plugin = _write(tmp_path, "plain.py", _NO_DECORATOR)
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "plugin", str(plugin)])
        assert result.exit_code == 0, result.stdout
        assert f"plugin: {plugin}" in result.stdout
        assert "profile:" not in result.stdout
        assert "summary:" in result.stdout

    def test_human_output_renders_info_finding(self, tmp_path: Path) -> None:
        """A decorator-less module renders DOC-PS-101 as an info finding."""
        plugin = _write(tmp_path, "plain.py", _NO_DECORATOR)
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "plugin", str(plugin)])
        assert result.exit_code == 0, result.stdout
        assert "[info] DOC-PS-101" in result.stdout
        assert "remediation:" in result.stdout

    def test_human_output_no_findings_marker(self, tmp_path: Path) -> None:
        """A clean plugin shows ``(no findings)``."""
        plugin = _write(tmp_path, "clean_plugin.py", _CLEAN_PLUGIN)
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "plugin", str(plugin)])
        assert result.exit_code == 0, result.stdout
        assert "(no findings)" in result.stdout


# ─────────── 4. CI exit-code contract ───────────


class TestCiExitCodes:
    def test_ci_mode_exits_1_on_errors(self, tmp_path: Path) -> None:
        """Syntax error + ``--ci`` → exit 1."""
        plugin = _write(tmp_path, "broken.py", _SYNTAX_ERROR)
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "plugin", str(plugin), "--ci"])
        assert result.exit_code == 1

    def test_ci_mode_exits_0_when_clean(self, tmp_path: Path) -> None:
        """Clean plugin + ``--ci`` → exit 0."""
        plugin = _write(tmp_path, "clean_plugin.py", _CLEAN_PLUGIN)
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "plugin", str(plugin), "--ci"])
        assert result.exit_code == 0

    def test_no_ci_mode_exits_0_on_errors(self, tmp_path: Path) -> None:
        """Without ``--ci`` errors do NOT bump the exit code."""
        plugin = _write(tmp_path, "broken.py", _SYNTAX_ERROR)
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "plugin", str(plugin)])
        assert result.exit_code == 0

    def test_ci_mode_info_only_exits_0(self, tmp_path: Path) -> None:
        """Info findings (DOC-PS-101) do NOT trip CI — only errors do."""
        plugin = _write(tmp_path, "plain.py", _NO_DECORATOR)
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "plugin", str(plugin), "--ci"])
        assert result.exit_code == 0


# ─────────── 5. Bad input ───────────


class TestBadInput:
    def test_missing_plugin_file_exits_2(self) -> None:
        """Nonexistent plugin path → exit 2, no doctor pass runs."""
        app = _build_app()
        _register(app)
        runner = CliRunner()
        result = runner.invoke(
            app, ["doctor", "plugin", "/definitely/does/not/exist.py"]
        )
        assert result.exit_code == 2


# ─────────── 6. I-HPC-7 read-only invariant ───────────


class TestReadOnlyInvariant:
    def test_no_journal_writes_in_module(self) -> None:
        """The doctor CLI module imports no journal / session / network writers."""
        source = Path(profile_module.__file__).read_text(encoding="utf-8")
        forbidden = [
            "lca.session",
            "lca.journal",
            "Session.append",
            "FactGateway",
            "write_journal",
            "append_event",
            "RunStore",
            "EnvelopeBus",
            "EventBus",
            "urllib.request",
            "urllib3",
            "httpx.",
            "requests.",
        ]
        for needle in forbidden:
            assert needle not in source, (
                f"doctor CLI must not import {needle!r} (I-HPC-7 read-only)"
            )
