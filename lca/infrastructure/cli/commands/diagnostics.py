"""Diagnostic commands: ``diagnose`` + 4 pattern aliases."""

from __future__ import annotations

from pathlib import Path

import typer

from lca.infrastructure.cli.commands._shared import resolve_diagnose_journal_path


def register(app: typer.Typer) -> None:
    """Register diagnostic commands on the typer app."""

    @app.command()
    def diagnose(
        problem: str = typer.Argument(
            ...,
            help=(
                "Diagnostic pattern to run: model-not-seen | loop-stuck | "
                "memory-poisoned | approval-rejected"
            ),
        ),
        trace_id: str = typer.Option(
            None, "--trace-id", help="Limit the scan to a specific trace id"
        ),
        expected_kind: str = typer.Option(
            "",
            "--expected-kind",
            help="For model-not-seen: the manifest kind the model should have seen",
        ),
        window: int = typer.Option(
            10, "--window", help="For loop-stuck: the recent-tool window to inspect"
        ),
        journal: Path = typer.Option(  # noqa: B008
            None,
            "--journal",
            help=(
                "Path to a journal jsonl file (defaults to "
                "traces/runs/<trace_id>/journal.json, journal.raw.jsonl, or "
                "traces/lca_journal.jsonl)"
            ),
        ),
    ) -> None:
        """Run a v3 diagnostic pattern against a journal."""
        from lca.infrastructure.observability.diagnostics import (
            DiagnosePattern,
        )
        from lca.infrastructure.observability.diagnostics import (
            diagnose as run_diagnose,
        )
        from lca.infrastructure.observability.journal.engine.engine import RunStore
        from lca.infrastructure.observability.journal.engine.journal_io import read_journal

        pattern_key = problem.strip().lower()
        aliases: dict[str, str] = {
            "model-not-seen": DiagnosePattern.MODEL_NOT_SEEN.value,
            "loop-stuck": DiagnosePattern.LOOP_STUCK.value,
            "memory-poisoned": DiagnosePattern.MEMORY_POISONED.value,
            "approval-rejected": DiagnosePattern.APPROVAL_REJECTED.value,
        }
        if pattern_key not in aliases:
            print(f"Unknown pattern {problem!r}; expected one of {sorted(aliases)}")
            raise typer.Exit(1)
        canonical = aliases[pattern_key]

        journal_path = resolve_diagnose_journal_path(journal, trace_id)
        if journal_path is None or not journal_path.exists():
            print(
                "No journal file found. Pass --journal <path> or set --trace-id "
                "(looks under traces/runs/)."
            )
            raise typer.Exit(1)

        store = RunStore()
        for stamped in read_journal(journal_path):
            store.append(stamped.event)

        pattern = DiagnosePattern(canonical)
        report = run_diagnose(
            store,
            pattern=pattern,
            trace_id=trace_id or None,
            expected_kind=expected_kind,
            window=window,
        )
        if report.ok:
            print(f"OK ({pattern.value}): no findings.")
            raise typer.Exit(0)
        print(f"Pattern: {pattern.value}")
        print(f"Journal: {journal_path}")
        if trace_id:
            print(f"Trace: {trace_id}")
        print()
        for finding in report.findings:
            print(f"  [{finding.severity.upper()}] {finding.summary}")
            if finding.evidence_refs:
                print(f"    refs: seq={','.join(str(s) for s in finding.evidence_refs)}")
            if finding.detail:
                print(f"    detail: {finding.detail}")
        raise typer.Exit(2 if any(f.severity == "high" for f in report.findings) else 1)

    @app.command(name="diagnose-model-not-seen")
    def diagnose_model_not_seen_alias(
        trace_id: str = typer.Option(None, "--trace-id"),
        expected_kind: str = typer.Option(
            "", "--expected-kind", help="Manifest kind the model should have seen"
        ),
        journal: Path = typer.Option(None, "--journal"),  # noqa: B008
    ) -> None:
        """Alias for ``diagnose model-not-seen``."""
        diagnose(
            problem="model-not-seen",
            trace_id=trace_id,
            expected_kind=expected_kind,
            journal=journal,
        )

    @app.command(name="diagnose-loop-stuck")
    def diagnose_loop_stuck_alias(
        trace_id: str = typer.Option(None, "--trace-id"),
        window: int = typer.Option(10, "--window"),
        journal: Path = typer.Option(None, "--journal"),  # noqa: B008
    ) -> None:
        """Alias for ``diagnose loop-stuck``."""
        diagnose(
            problem="loop-stuck",
            trace_id=trace_id,
            window=window,
            journal=journal,
        )

    @app.command(name="diagnose-memory-poisoned")
    def diagnose_memory_poisoned_alias(
        journal: Path = typer.Option(None, "--journal"),  # noqa: B008
    ) -> None:
        """Alias for ``diagnose memory-poisoned``."""
        diagnose(problem="memory-poisoned", journal=journal)

    @app.command(name="diagnose-approval-rejected")
    def diagnose_approval_rejected_alias(
        journal: Path = typer.Option(None, "--journal"),  # noqa: B008
    ) -> None:
        """Alias for ``diagnose approval-rejected``."""
        diagnose(problem="approval-rejected", journal=journal)
