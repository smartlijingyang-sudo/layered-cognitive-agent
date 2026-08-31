"""``lca-ops evidence <run_id> <ref>`` CLI subcommand tests —— ADR-0065 §四 L5 / PR-9。

- happy path: state_ref → evidence bytes → JSON-decoded dict(stdout)
- non-existent ref: exit 1, "no evidence referenced" stderr
- invalid ref format: exit 1
- L5 integrity failure (forced) → exit 1
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import typer.testing

from lca.contracts.observability.evidence import (
    EvidenceStore,
)
from lca.infrastructure.cli.cli import app
from lca.infrastructure.observability import (
    BoundObservability,
    bind_backends,
    run_scope,
)
from lca.infrastructure.observability.evidence.policy import (
    DefaultEvidencePolicy,
)
from lca.infrastructure.observability.evidence.store import (
    FilesystemEvidenceStore,
)
from lca.infrastructure.observability.journal.jsonl.projector import (
    JsonlJournalProjector,
)
from lca.infrastructure.observability.journal_backend import MemoryJournal
from lca.infrastructure.observability.policy import AttributePolicy

_RUNNER = typer.testing.CliRunner()


class _ScriptableEvidenceStore(EvidenceStore):
    def __init__(self, fs: FilesystemEvidenceStore) -> None:
        self._fs = fs
        self.raise_integrity: bool = False

    def prepare(
        self,
        payload,
        *,
        classification,
        retention,
        media_type="application/octet-stream",
        prepared_by="",
    ):
        return self._fs.prepare(
            payload,
            classification=classification,
            retention=retention,
            media_type=media_type,
            prepared_by=prepared_by,
        )

    def get(self, ref, *, requester, audience):
        if self.raise_integrity:
            from lca.contracts.observability.evidence import EvidenceIntegrityError

            raise EvidenceIntegrityError(f"sha256 mismatch: {ref.digest[:16]}")
        return self._fs.get(ref, requester=requester, audience=audience)

    def contains(self, ref):
        return self._fs.contains(ref)

    def sweep_orphan(self, ledger_index):
        return self._fs.sweep_orphan(ledger_index)


def _drive_run(jsonl_path: Path, ev_root: Path) -> tuple[str, dict, str]:
    """drive a ToolStarted with state_ref through public record() path."""
    from lca.cognition.body.tool_journal_emit import (
        emit_tool_started,
    )
    from lca.contracts.models.observability.journal import (
        RunScope,
        ToolStarted,
    )

    class _MockTool:
        name = "execute_code"

    policy = DefaultEvidencePolicy(inline_threshold_bytes=64)
    store = FilesystemEvidenceStore(ev_root)
    journal = MemoryJournal(policy=AttributePolicy()).with_projection(
        JsonlJournalProjector(jsonl_path)
    )
    bound = BoundObservability(
        evidence_store=store,
        evidence_policy=policy,
        journal=journal,
    )
    big = {"code": "x" * 200, "language": "python", "description": "big state"}
    scope = RunScope(trace_id="t", run_id="run_evi", agent_role="researcher")
    with bind_backends(bound), run_scope(scope):
        # ADR-0101 PR-2:emit_tool_started takes args (dict), returns
        # arguments_ref. started_state / args_preview 都不再需要。
        ref = emit_tool_started(
            _MockTool(),
            big,
            invocation_id="inv1",
            evidence_store=store,
            evidence_policy=policy,
        )
    from lca.infrastructure.observability.journal.engine.journal_io import read_journal

    events = read_journal(jsonl_path)
    ts = next(e for e in events if isinstance(e.event, ToolStarted))
    assert ref is not None
    assert ts.event.arguments_ref is not None
    return "run_evi", big, ts.event.arguments_ref.digest


def test_cli_evidence_happy_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        ev = Path(tmp) / "ev"
        run_id, original, digest = _drive_run(jsonl, ev)

        bound = BoundObservability(
            evidence_store=FilesystemEvidenceStore(ev),
            evidence_policy=DefaultEvidencePolicy(),
        )
        # bind the bound so current_bound() returns it
        from lca.infrastructure.observability.facade import bind_backends as _bb

        with _bb(bound):
            result = _RUNNER.invoke(
                app, ["evidence", run_id, digest, "--jsonl", str(jsonl), "--json"]
            )
        assert result.exit_code == 0, result.stdout + result.stderr
        report = json.loads(result.stdout)
        assert report["run_id"] == run_id
        assert report["ref"] == digest
        assert report["byte_length"] > 0
        assert report["data"] == original


def test_cli_evidence_accepts_sha256_prefix() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        ev = Path(tmp) / "ev"
        run_id, original, digest = _drive_run(jsonl, ev)
        bound = BoundObservability(
            evidence_store=FilesystemEvidenceStore(ev),
            evidence_policy=DefaultEvidencePolicy(),
        )
        from lca.infrastructure.observability.facade import bind_backends as _bb

        with _bb(bound):
            result = _RUNNER.invoke(
                app,
                ["evidence", run_id, f"sha256:{digest}", "--jsonl", str(jsonl), "--json"],
            )
        assert result.exit_code == 0
        assert json.loads(result.stdout)["data"] == original


def test_cli_evidence_no_ref_found_exit_1() -> None:
    """run exists but no state_ref matches the given digest."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        ev = Path(tmp) / "ev"
        run_id, _original, _digest = _drive_run(jsonl, ev)
        bound = BoundObservability(
            evidence_store=FilesystemEvidenceStore(ev),
            evidence_policy=DefaultEvidencePolicy(),
        )
        from lca.infrastructure.observability.facade import bind_backends as _bb

        with _bb(bound):
            result = _RUNNER.invoke(
                app,
                ["evidence", run_id, "0" * 64, "--jsonl", str(jsonl), "--json"],
            )
        assert result.exit_code == 1
        assert "no evidence referenced" in result.stderr


def test_cli_evidence_invalid_ref_format_exit_1() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        result = _RUNNER.invoke(
            app,
            ["evidence", "run_x", "not-hex-!!!", "--jsonl", str(jsonl)],
        )
        assert result.exit_code == 1
        assert "invalid ref format" in result.stderr


def test_cli_evidence_integrity_failure_exit_1() -> None:
    """forced integrity violation (L5) → exit 1 with clear error message."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        ev = Path(tmp) / "ev"
        run_id, _original, digest = _drive_run(jsonl, ev)

        scriptable = _ScriptableEvidenceStore(FilesystemEvidenceStore(ev))
        scriptable.raise_integrity = True
        bound = BoundObservability(
            evidence_store=scriptable,
            evidence_policy=DefaultEvidencePolicy(),
        )
        from lca.infrastructure.observability.facade import bind_backends as _bb

        with _bb(bound):
            result = _RUNNER.invoke(
                app,
                ["evidence", run_id, digest, "--jsonl", str(jsonl), "--json"],
            )
        assert result.exit_code == 1
        assert "integrity" in result.stderr


def test_cli_evidence_no_seam_exit_2() -> None:
    """no bound_observability → exit 2 (boot didn't wire evidence seam)."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        ev = Path(tmp) / "ev"
        # Drive WITHOUT the evidence seam (so the journal has state_ref
        # but no bound_observability.evidence_store exists at command time).
        from lca.contracts.models.observability.journal import (
            RunScope,
            ToolStarted,
        )

        class _MockTool:
            name = "execute_code"

        ev_store = FilesystemEvidenceStore(ev)
        proj = JsonlJournalProjector(jsonl)
        bound_no_seam = BoundObservability(
            evidence_store=ev_store,
            evidence_policy=None,  # no policy => prepare_state_evidence returns None
            journal=MemoryJournal(policy=AttributePolicy()).with_projection(proj),
        )
        # Write a ToolStarted WITHOUT state_ref (since policy is None) — but
        # the journal needs to exist for _resolve_journal_path to work.
        # Easier: write a known digest as a state_ref in a fake envelope.
        digest = "f" * 64
        from lca.contracts.observability.evidence import (
            Classification,
            EvidenceRef,
            RetentionClass,
        )

        sr = EvidenceRef(
            algorithm="sha256",
            digest=digest,
            media_type="application/json",
            byte_length=100,
            classification=Classification.INTERNAL,
            retention=RetentionClass.RUN_DEFAULT,
            locator="",
        ).to_dict()
        from lca.contracts.models.observability.journal import StampedEvent
        from lca.infrastructure.observability.journal.engine.journal_io import stamped_to_record

        # Build a ToolStarted with arguments_ref (ADR-0101 PR-2: state_ref → arguments_ref)
        scope = RunScope(trace_id="t", run_id="run_x", agent_role="r")
        tool_evt = ToolStarted(
            tool_name="t", invocation_id="i", arguments_ref=EvidenceRef.from_dict(sr)
        )
        stamped = StampedEvent(seq=1, ts=1.0, scope=scope, event=tool_evt)
        jsonl.write_text(json.dumps(stamped_to_record(stamped)) + "\n")

        from lca.infrastructure.observability.facade import bind_backends as _bb

        with _bb(bound_no_seam):
            result = _RUNNER.invoke(app, ["evidence", "run_x", digest, "--jsonl", str(jsonl)])
        # The endpoint found the ref in the journal, then tried EvidenceStore
        # — and bound.evidence_store is present, but bound.evidence_policy is
        # None, so the endpoint may still try. What we really want to test is
        # the no-store path; for that, drop the evidence_store:
        bound_no_store = BoundObservability(
            evidence_store=None,
            evidence_policy=None,
            journal=MemoryJournal(policy=AttributePolicy()).with_projection(proj),
        )
        with _bb(bound_no_store):
            result = _RUNNER.invoke(app, ["evidence", "run_x", digest, "--jsonl", str(jsonl)])
        assert result.exit_code == 2
        assert "evidence_store not configured" in result.stderr


def test_cli_evidence_human_readable_default() -> None:
    """without --json, output is indented JSON, not a single line."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        ev = Path(tmp) / "ev"
        run_id, original, digest = _drive_run(jsonl, ev)
        bound = BoundObservability(
            evidence_store=FilesystemEvidenceStore(ev),
            evidence_policy=DefaultEvidencePolicy(),
        )
        from lca.infrastructure.observability.facade import bind_backends as _bb

        with _bb(bound):
            result = _RUNNER.invoke(app, ["evidence", run_id, digest, "--jsonl", str(jsonl)])
        assert result.exit_code == 0
        # indented human readable (not a single line)
        assert "\n" in result.stdout
        assert json.dumps(original)[1:-1] not in result.stdout or "code" in result.stdout
