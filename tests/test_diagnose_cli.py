"""Phase J — lca-ops diagnose CLI subcommand (spec §24.5).

The CLI drives the four canonical diagnostic patterns:

- ``diagnose model-not-seen``   — manifest missing a kind
- ``diagnose loop-stuck``       — repeated tool calls / no progress
- ``diagnose memory-poisoned``  — poisoned record reached the prompt
- ``diagnose approval-rejected`` — ApprovalResolved(false) emitted

Each pattern also has a top-level alias (``diagnose-model-not-seen``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lca.infrastructure.observability.journal.journal_io import stamped_to_record
from lca.infrastructure.ops.cli import app

runner = CliRunner()


def _command_names() -> set[str]:
    """Return the set of top-level command names registered on the CLI app.

    Typer defaults ``cmd.name`` to ``None`` and derives the name from
    the callback function name, so we mirror that.
    """
    names: set[str] = set()
    for cmd in app.registered_commands:
        if cmd.name is not None:
            names.add(cmd.name)
        elif cmd.callback is not None:
            names.add(cmd.callback.__name__)
    return names


def _write_journal(path: Path, *events) -> Path:
    """Serialize a sequence of journal events to a jsonl file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for seq, event in enumerate(events, start=1):
            from lca.contracts.models.observability.journal import (
                RunScope,
                StampedEvent,
            )

            stamped = StampedEvent(seq=seq, ts=float(seq), scope=RunScope(), event=event)
            f.write(json.dumps(stamped_to_record(stamped), ensure_ascii=False))
            f.write("\n")
    return path


class TestDiagnoseCommandExists:
    """The CLI must register the ``diagnose`` command + aliases."""

    def test_diagnose_command_exists(self) -> None:
        names = _command_names()
        assert "diagnose" in names, (
            f"expected 'diagnose' in registered commands; got {sorted(names)}"
        )

    def test_diagnose_aliases_registered(self) -> None:
        names = _command_names()
        for alias in (
            "diagnose-model-not-seen",
            "diagnose-loop-stuck",
            "diagnose-memory-poisoned",
            "diagnose-approval-rejected",
        ):
            assert alias in names, f"missing alias command: {alias}"

    def test_diagnose_routes_to_correct_function(self, tmp_path: Path) -> None:
        """Each pattern name dispatches to the matching diagnose_* fn.

        Build a tiny journal containing the events the four patterns
        react to, then invoke each sub-pattern.  The output must
        mention the pattern (proving the dispatch reached the right
        function).
        """
        from lca.contracts.models.observability.journal import (
            ApprovalResolved,
            InboxFollowupCreated,
            MemoryCommitted,
        )

        journal = tmp_path / "run.journal"
        _write_journal(
            journal,
            InboxFollowupCreated(inbox_id="x", actor="user", target="t", priority="p"),
            ApprovalResolved(envelope_id="env-1", approved=False, resolver="user"),
            MemoryCommitted(layer="procedural"),
        )

        for pattern, expect_token in (
            ("model-not-seen", "model_not_seen"),
            ("loop-stuck", "loop_stuck"),
            ("memory-poisoned", "memory_poisoned"),
            ("approval-rejected", "approval_rejected"),
        ):
            result = runner.invoke(app, ["diagnose", pattern, "--journal", str(journal)])
            assert expect_token in result.stdout, (
                f"pattern {pattern}: expected token {expect_token!r} "
                f"in stdout, got {result.stdout[:300]}"
            )


class TestDiagnoseAliasExecution:
    """Each alias runs the same diagnostic, just with no positional arg."""

    @pytest.fixture
    def journal(self, tmp_path: Path) -> Path:
        from lca.contracts.models.observability.journal import (
            ApprovalResolved,
            MemoryCommitted,
        )

        path = tmp_path / "run.journal"
        return _write_journal(
            path,
            ApprovalResolved(envelope_id="e", approved=False, resolver="user"),
            MemoryCommitted(layer="procedural"),
        )

    def test_diagnose_model_not_seen_help(self) -> None:
        """The alias command is registered and accepts the expected opts."""
        names = _command_names()
        assert "diagnose-model-not-seen" in names

    def test_diagnose_loop_stuck_help(self) -> None:
        names = _command_names()
        assert "diagnose-loop-stuck" in names

    def test_diagnose_memory_poisoned_help(self) -> None:
        names = _command_names()
        assert "diagnose-memory-poisoned" in names

    def test_diagnose_approval_rejected_help(self) -> None:
        names = _command_names()
        assert "diagnose-approval-rejected" in names

    def test_diagnose_approval_rejected_runs(self, journal: Path) -> None:
        result = runner.invoke(app, ["diagnose-approval-rejected", "--journal", str(journal)])
        # Should produce output mentioning the pattern.
        assert "approval_rejected" in result.stdout


class TestDiagnoseUnknownPattern:
    def test_unknown_pattern_exits_nonzero(self, tmp_path: Path) -> None:
        journal = tmp_path / "run.journal"
        journal.write_text("")
        result = runner.invoke(app, ["diagnose", "no-such-pattern", "--journal", str(journal)])
        assert result.exit_code != 0
        assert "Unknown pattern" in result.stdout


class TestDiagnoseMissingJournal:
    def test_missing_journal_exits_nonzero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["diagnose", "model-not-seen"])
        # No journal found in cwd; the command must exit non-zero.
        assert result.exit_code != 0
        assert "No journal" in result.stdout


@pytest.fixture
def _tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path
