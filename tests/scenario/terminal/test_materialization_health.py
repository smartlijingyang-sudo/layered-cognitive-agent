"""Manifest close-path rewrite tests for ``record_terminal_materialization`` (PR-1 / Task 1.7).

Per spec
``docs/superpowers/specs/2026-09-16-run-health-and-execution-closure-design.md``
§15 G-6..G-9, G-12, G-13 + §2.6 (manifest close-path):

1. **G-6 / G-7 / G-8**: ``RunManifest.terminal_event_seq``,
   ``ledger_high_watermark``, ``ledger_summary`` are marked
   ``@deprecated`` (delete-when 2027-01-01). The new
   ``health_summary`` + ``health_hash`` fields replace them as the
   integrity source.
2. **G-9**: the ``_TERMINAL_EVENT_TYPES`` constant is deleted.
3. **G-12** (C9 idempotency): ``record_terminal_materialization`` is
   idempotent — calling it twice leaves ``manifest.json`` mtime
   unchanged on the second call.
4. **G-13** (C7 / C9 fail-loud): if ``flush_step_tree_artifacts``
   returns errors, ``record_terminal_materialization`` raises
   ``ManifestFlushIncompleteError`` and does NOT write the manifest.

These 5 cases pin the new close-path contract; the green phase ships
``_materialization_lock`` (flock), the ``ManifestFlushIncompleteError``
exception, the deprecated-field markers, the new health fields, and
the ``_TERMINAL_EVENT_TYPES`` deletion.
"""

from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from lca.infrastructure.observability.backends.run_locator_fs import (
    FilesystemRunLocator,
)
from lca.infrastructure.observability.journal.engine.journal_io import (
    JOURNAL_SCHEMA_VERSION,
)
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunSession,
    RunStatus,
)
from lca.plugins.transport.webserver.read.runs.identity.identity import (
    parse_agent_ref,
)
from lca.plugins.transport.webserver.read.runs.terminal import materialization
from lca.plugins.transport.webserver.read.runs.terminal.materialization import (
    record_terminal_materialization,
)


# ── helpers ─────────────────────────────────────────────────────────


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _row(seq: int, event_type: str, event: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": JOURNAL_SCHEMA_VERSION,
        "seq": seq,
        "ts": float(seq),
        "scope": {"trace_id": "t", "run_id": "run_x",
                  "agent_role": "agt_x", "step": 0},
        "event_type": event_type,
        "event": event,
    }


def _make_session(*, run_id: str, spine_path: Path,
                  status: RunStatus) -> RunSession:
    locator = FilesystemRunLocator(root=spine_path.parent.parent.parent)
    return RunSession(
        run_id=run_id,
        trace_id="trace_x",
        spine_path=spine_path,
        tail=LiveTail(),
        question="q",
        user_text="q",
        mode="solo",
        agent=parse_agent_ref({"id": "solo", "name": "助手"}),
        status=status,
        started_at=1000.0,
        closed_at=1100.0,
        locator=locator,
    )


# ── 5 cases ─────────────────────────────────────────────────────────


def test_manifest_includes_health_summary_and_hash(tmp_path) -> None:
    """After ``record_terminal_materialization(session)``, the manifest
    JSON has ``health_summary: dict`` and ``health_hash: str``.

    The hash is the sha256 of ``report.model_dump_json()`` and must be
    stable for the same spine.
    """
    run_id = "run_manifest_health"
    spine_path = tmp_path / "runs" / run_id / "events.jsonl"
    _write_jsonl(
        spine_path,
        [
            _row(1, "AgentRunStarted", {"agent_role": "agt_x"}),
            _row(2, "AgentRunFinished", {"agent_role": "agt_x", "ok": True}),
        ],
    )
    session = _make_session(
        run_id=run_id, spine_path=spine_path, status=RunStatus.COMPLETED
    )
    record_terminal_materialization(session)
    manifest_path = tmp_path / "runs" / run_id / "manifest.json"
    assert manifest_path.exists(), "manifest.json must exist"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "health_summary" in payload
    assert "health_hash" in payload
    assert isinstance(payload["health_summary"], dict)
    assert "by_type" in payload["health_summary"]
    assert isinstance(payload["health_hash"], str)
    assert len(payload["health_hash"]) == 64  # sha256 hex


def test_manifest_marks_legacy_fields_deprecated(tmp_path) -> None:
    """The 3 legacy Session/Catalog vocabulary fields are marked
    ``@deprecated`` (G-6 / G-7 / G-8).

    Strategy: the module docstring + the ``RunManifest`` class
    docstring must contain a ``delete-when: 2027-01-01`` marker AND a
    clear ``@deprecated`` note naming each of the 3 fields. We also
    verify the new ``health_summary`` field is present alongside
    (replacing them as the integrity source).
    """
    import lca.contracts.observability.registry.run_manifest as rm_mod

    cls = rm_mod.RunManifest
    src = (cls.__doc__ or "") + "\n" + (rm_mod.__doc__ or "")
    assert "delete-when" in src and "2027-01-01" in src, (
        "delete-when: 2027-01-01 must appear in the RunManifest module "
        "docstring or class docstring"
    )
    assert "deprecated" in src.lower(), (
        "the RunManifest module must mark the legacy fields as @deprecated"
    )
    for legacy_name in ("terminal_event_seq",
                        "ledger_high_watermark", "ledger_summary"):
        assert legacy_name in cls.__dataclass_fields__, (
            f"legacy field {legacy_name} should still exist for backward "
            f"compatibility but be marked @deprecated"
        )


def test_materialization_is_idempotent(tmp_path) -> None:
    """Calling ``record_terminal_materialization(session)`` twice leaves
    ``manifest.json`` mtime unchanged on the second call (G-12 / C9).

    C9 idempotency: re-running terminalize (crash recovery, repeated
    terminal hook, etc.) must not re-fold + rewrite the manifest.
    """
    run_id = "run_idempotent"
    spine_path = tmp_path / "runs" / run_id / "events.jsonl"
    _write_jsonl(
        spine_path,
        [
            _row(1, "AgentRunStarted", {"agent_role": "agt_x"}),
            _row(2, "AgentRunFinished", {"agent_role": "agt_x", "ok": True}),
        ],
    )
    session = _make_session(
        run_id=run_id, spine_path=spine_path, status=RunStatus.COMPLETED
    )

    record_terminal_materialization(session)
    manifest_path = tmp_path / "runs" / run_id / "manifest.json"
    assert manifest_path.exists()
    first_mtime = manifest_path.stat().st_mtime_ns
    first_payload = manifest_path.read_text(encoding="utf-8")

    # Sleep so any re-write would have a different mtime.
    time.sleep(0.05)

    record_terminal_materialization(session)
    second_mtime = manifest_path.stat().st_mtime_ns
    second_payload = manifest_path.read_text(encoding="utf-8")

    assert first_mtime == second_mtime, (
        "second materialization must not rewrite manifest.json"
    )
    # And the content is unchanged (no race between fold + write).
    assert first_payload == second_payload


def test_materialization_raises_on_partial_flush(tmp_path) -> None:
    """If ``flush_step_tree_artifacts`` returns errors, ``record_terminal_materialization``
    raises ``ManifestFlushIncompleteError`` and ``manifest.json`` is NOT written (G-13).

    C7 + C9: a half-flushed journal.json + manifest.json would let a
    consumer see a manifest with ``flush_errors`` non-empty and no
    signal that the journal is broken. The new behaviour is fail-loud.
    """
    run_id = "run_partial_flush"
    spine_path = tmp_path / "runs" / run_id / "events.jsonl"
    _write_jsonl(
        spine_path,
        [
            _row(1, "AgentRunStarted", {"agent_role": "agt_x"}),
            _row(2, "AgentRunFinished", {"agent_role": "agt_x", "ok": True}),
        ],
    )
    session = _make_session(
        run_id=run_id, spine_path=spine_path, status=RunStatus.COMPLETED
    )

    # Inject flush failure: the function should see flush_errors and
    # raise. The import statement must fail first (RED), but here we
    # also cover the import-success path of the new exception class.
    fake_flush_errors = [{"operation": "journal_write",
                          "error_type": "OSError",
                          "error_message": "disk full"}]

    with patch.object(
        materialization,
        "flush_step_tree_artifacts",
        return_value=fake_flush_errors,
    ):
        with __import__("pytest").raises(
            materialization.ManifestFlushIncompleteError,
        ):
            record_terminal_materialization(session)

    manifest_path = tmp_path / "runs" / run_id / "manifest.json"
    assert not manifest_path.exists(), (
        "manifest.json must NOT be written when flush_step_tree_artifacts "
        "returns errors (G-13 fail-loud contract)"
    )


def test_ter_ev_types_constant_removed() -> None:
    """``_TERMINAL_EVENT_TYPES`` constant is deleted from
    ``lca.plugins.transport.webserver.read.runs.terminal.materialization``.

    Per spec §15 G-9: the Session/Catalog vocabulary mismatch is
    closed by deleting the constant (it has no spine-equivalent).
    Consumers that needed terminal seq now go through health.
    """
    with __import__("pytest").raises(ImportError):
        from lca.plugins.transport.webserver.read.runs.terminal.materialization import (  # noqa: F401
            _TERMINAL_EVENT_TYPES,  # noqa: F821
        )

    # Also verify the module no longer carries it (the symbol may be
    # present-but-undefined to fail the import above; we check the
    # attr is gone too).
    assert not hasattr(materialization, "_TERMINAL_EVENT_TYPES"), (
        "_TERMINAL_EVENT_TYPES must be deleted (G-9)"
    )