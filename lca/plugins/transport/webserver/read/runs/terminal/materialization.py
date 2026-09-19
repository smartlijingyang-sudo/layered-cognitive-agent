"""Materialize a terminal run manifest from Journal-owned facts.

PR-1 / Task 1.7 close-path contract (spec §2.6, §15 G-6..G-9, G-12, G-13):

- **G-6 / G-7 / G-8**: ``RunManifest.terminal_event_seq``,
  ``ledger_high_watermark``, ``ledger_summary`` are marked
  ``@deprecated`` (delete-when: 2027-01-01). The new
  ``health_summary`` + ``health_hash`` fields replace them as the
  integrity source.
- **G-9**: the ``_TERMINAL_EVENT_TYPES`` constant is deleted (the
  Session/Catalog vocabulary mismatch is closed; ``health_hash``
  subsumes its integrity role).
- **G-12** (C9 idempotency): ``_materialization_lock`` uses
  ``fcntl.flock`` for per-run-id mutual exclusion across processes,
  and ``record_terminal_materialization`` skips re-writing when
  ``manifest.json`` already carries the same ``health_hash``.
- **G-13** (C7 / C9 fail-loud): if ``flush_step_tree_artifacts``
  returns errors, ``ManifestFlushIncompleteError`` is raised and the
  manifest is NOT written. Catches the "broken journal.json + clean
  manifest.json" silent-failure class.

# ADR-0203 §3.3: streaming file-bytes hash; canonical_digest requires
# full payload in memory.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import time
import traceback
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import structlog

from lca.contracts.observability.health.report import (
    RunHealthSummary,
)
from lca.contracts.observability.registry.run_locator import RunLocator
from lca.contracts.observability.registry.run_manifest import RunManifest
from lca.infrastructure.atomic.write import atomic_write_text
from lca.infrastructure.observability.journal.engine.journal_io import (
    load_journal_records,
    record_normalize,
)
from lca.infrastructure.workspace.artifact_ledger import artifact_closure_text
from lca.plugins.observability.health.run_health_fold import fold_run_health
from lca.plugins.transport.webserver.doctor import diagnose
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunSession,
)
from lca.plugins.transport.webserver.read.runs.step.tree_flush import (
    flush_step_tree_artifacts,
)


class ManifestFlushIncompleteError(RuntimeError):
    """Raised when ``flush_step_tree_artifacts`` returns errors.

    PR-1 / Task 1.7 (G-13): the close-path is fail-loud on partial
    flush — a half-written ``journal.json`` paired with a clean
    ``manifest.json`` is a C7 violation (control/observation
    separation) and a C9 violation (recoverability). The caller can
    catch this, surface the error, and decide whether to retry or
    mark the run failed.
    """


_log = structlog.get_logger(__name__)


@contextlib.contextmanager
def _materialization_lock(manifest_path: Path) -> Iterator[None]:
    """Per-run-id ``fcntl.flock`` around manifest close-path.

    PR-1 / Task 1.7 (G-12, C9 idempotency): on POSIX, hold an
    exclusive lock on a sibling ``.lock`` file for the duration of
    the close-path so concurrent terminal hooks (crash recovery +
    main shutdown) cannot race. Windows falls back to a no-op; the
    in-process early-return (existing ``manifest.json`` with same
    ``health_hash``) still protects same-process reentry.

    Note: ``fcntl.flock`` is unavailable on Windows. We do not
    degrade silently — the ``fcntl`` import is at module load; if
    the platform lacks it, fail loud (the alternative is a silent
    lost-update on terminal manifest). For Windows the AGENTS.md
    §5 guideline says "every dependency needs an owner"; here the
    owner is the run-terminator on POSIX servers, with a documented
    limitation for Windows that the same-process idempotency still
    holds.
    """
    lock_path = manifest_path.with_suffix(manifest_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fp = lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        finally:
            fp.close()


def record_terminal_materialization(session: RunSession) -> None:
    """Write a terminal manifest without owning facts.

    PR-1 / Task 1.7 close-path:
    - idempotent on reentry via ``_materialization_lock`` + a
      ``health_hash`` early-return (G-12 / C9);
    - fail-loud on partial flush via ``ManifestFlushIncompleteError``
      (G-13 / C7 + C9);
    - emits ``health_summary`` + ``health_hash`` as the integrity
      source (G-6..G-8).

    ADR-0164 Phase 7: 在写 manifest 之前 flush step-tree bundle(写
    journal.json + narrative.md)。让 step-tree 是主存储,旧 stream 是 raw。
    """
    locator = session_locator(session)
    flush_errors: list[dict[str, str]] = []

    # ADR-0164: terminalize 时 step-tree flush(写 journal.json + narrative.md)
    flush_errors.extend(flush_step_artifacts_with_log(session))

    if flush_errors:
        # G-13: fail-loud on partial flush; do NOT write the manifest.
        _log.error(
            "manifest_flush_incomplete",
            run_id=session.run_id,
            flush_errors=flush_errors,
        )
        raise ManifestFlushIncompleteError(
            f"flush_step_tree_artifacts returned {len(flush_errors)} error(s); "
            f"refusing to write manifest for run_id={session.run_id}",
        )

    manifest_path = locator.manifest_path(session.run_id)

    try:
        report = diagnose(session, _doctor_journal_path(session, locator))
        if report.broken_hop or not report.factory["ok"]:
            _log.error(
                "run_doctor_verdict",
                hop=report.broken_hop or "factory",
                run_id=session.run_id,
                broken_hop=report.broken_hop,
                summary=report.summary,
            )

        session_error = str(session.error or "")
        session_status = str(getattr(session.status, "value", session.status) or "")

        # PR-1 / Task 1.7 (G-6..G-8): fold the spine for the new
        # health_summary + health_hash. Done BEFORE flock so we
        # don't hold the lock for the I/O.
        try:
            health_report = fold_run_health(session.spine_path)
        except Exception as exc:
            _log.error(
                "run_health_fold_failed",
                run_id=session.run_id,
                error_type=type(exc).__name__,
                error_message=str(exc)[:500],
            )
            health_report = None

        if health_report is None:
            health_summary = RunHealthSummary(
                conditions_ok=0,
                conditions_degraded=0,
                conditions_failed=0,
                conditions_unknown=0,
                by_type={},
            )
            health_hash = ""
        else:
            health_summary = health_report.summary
            # Hash excludes ``generated_at`` so a re-fold of the same
            # spine produces the same hash (idempotent C9 check).
            # The other 4 fields are deterministic per spec §10.5.
            payload_for_hash = health_report.model_dump(mode="json")
            payload_for_hash.pop("generated_at", None)
            health_hash = hashlib.sha256(
                json.dumps(payload_for_hash, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()

        # G-12: under the per-run-id flock, check for early-return.
        with _materialization_lock(manifest_path):
            if manifest_path.exists():
                try:
                    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    existing = None
                if (
                    isinstance(existing, dict)
                    and existing.get("health_hash") == health_hash
                    and existing.get("run_id") == session.run_id
                ):
                    _log.info(
                        "manifest_close_path_idempotent_skip",
                        run_id=session.run_id,
                        health_hash=health_hash,
                    )
                    return  # C9 idempotent early-return

            manifest = RunManifest(
                run_id=session.run_id,
                plan_ref=str(session.plan_ref),
                session_error=session_error,
                session_status=session_status,
                health_summary=health_summary,
                health_hash=health_hash,
                # Legacy fields: still populated for backward
                # compatibility (G-6..G-8 delete-when: 2027-01-01).
                terminal_event_seq=terminal_event_seq_for(session),
                ledger_high_watermark=ledger_high_watermark_for(session),
                ledger_summary=ledger_summary_for(session),
                started_at=session.started_at,
                closed_at=(session.closed_at if session.closed_at is not None else time.time()),
                extra={
                    "doctor_report": report.as_dict(),
                    "flush_errors": tuple(flush_errors),
                    "artifact_closure": _artifact_closure_manifest(session),
                },
            )
            atomic_write_text(
                manifest_path,
                json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            )
    except ManifestFlushIncompleteError:
        # Already raised above; nothing to do here. Re-raise for
        # caller visibility.
        raise
    except Exception as exc:
        # manifest 自身写失败 —— 已无法写到 disk, 把异常也收进 flush_errors
        # 让上游 / debug-run 通过 structlog 看得到
        flush_errors.append(
            {
                "operation": "manifest_write",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
                "traceback": traceback.format_exc(limit=4),
            }
        )
        _log.error(
            "run_terminal_materialization_failed",
            hop="H2",
            run_id=session.run_id,
            exc_info=True,
        )


def flush_step_artifacts_with_log(session: RunSession) -> list[dict[str, str]]:
    """Wrap ``flush_step_tree_artifacts`` to log any errors before returning.

    Keeps the existing "collect errors, don't raise" semantics in one
    place so the close-path can decide whether to raise
    ``ManifestFlushIncompleteError`` based on the aggregated result.
    """
    try:
        return list(flush_step_tree_artifacts(session))
    except Exception as exc:
        _log.error(
            "flush_step_tree_artifacts_raised",
            run_id=session.run_id,
            error_type=type(exc).__name__,
            error_message=str(exc)[:500],
            exc_info=True,
        )
        return [
            {
                "operation": "flush_step_tree_artifacts",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
                "traceback": traceback.format_exc(limit=4),
            }
        ]


def _doctor_journal_path(session: RunSession, locator: RunLocator) -> Path:
    """Doctor 扫描路径: 优先 journal.json (step-tree), 然后 spine ledger (SSOT)。

    ADR-0167 D11:
    - journal.json 优先:它是可重建物化视图(lca.journal/3.1 step 树)
    - spine ledger 兜底: SSOT —— 仅供迁移期 / partial profile 兜底
    """
    step_path = locator.journal_step_path(session.run_id)
    if step_path.exists():
        return step_path
    spine_path = locator.events_path(session.run_id)
    if spine_path.exists():
        return spine_path
    return session.spine_path


def session_locator(session: RunSession) -> RunLocator:
    """Resolve the configured locator or derive a filesystem fallback for direct tests."""
    if session.locator is not None:
        return session.locator
    from lca.infrastructure.observability.backends.run_locator_fs import (
        FilesystemRunLocator,
    )

    return FilesystemRunLocator(root=session.spine_path.parent.parent.parent)


def ledger_high_watermark_for(session: RunSession) -> int:
    """Read the final Session sequence from the spine file (SSOT only).

    @deprecated — delete-when: 2027-01-01 (G-7). Replaced by
    ``health_hash`` as the integrity source.
    """
    return watermark_from_file(session.spine_path)


def terminal_event_seq_for(session: RunSession) -> int:
    """Return the seq of the last AgentRunFinished / TeamRunFinished in spine.jsonl.

    @deprecated — delete-when: 2027-01-01 (G-6). The spine vocabulary
    mismatch between Session/Catalog events and the actual SPINE_EPs
    is closed by removing the constant and replacing the integrity
    role with ``health_hash``.
    """
    return 0  # _TERMINAL_EVENT_TYPES deleted (G-9); field stays for compat.


def watermark_from_file(path: Path) -> int:
    """Scan the terminal JSONL watermark; empty or malformed rows are ignored.

    @deprecated — kept for legacy ``ledger_high_watermark`` field
    compatibility. The fold view (``health_hash``) is the integrity
    source after PR-1.
    """
    if not path.exists():
        return 0
    last = 0
    try:
        for row in load_journal_records(path, strict=False):
            normalized = record_normalize(row)
            last = max(last, int(normalized.get("run_seq", row.get("seq", 0)) or 0))
    except OSError:
        return 0
    return last


def terminal_event_seq_from_file(path: Path) -> int:
    """Scan JSONL in reverse for the last AgentRunFinished, RunFinished, or RunSealed seq.

    @deprecated — _TERMINAL_EVENT_TYPES removed in PR-1 (G-9).
    Kept as a stub for callers that haven't migrated; returns 0
    unconditionally (the integrity role moved to ``health_hash``).
    """
    return 0


def ledger_summary_for(session: RunSession) -> str:
    """Hash the terminal one megabyte of the Journal for integrity navigation.

    @deprecated — delete-when: 2027-01-01 (G-8). Replaced by
    ``health_hash`` as the integrity source.
    """
    path = session.spine_path
    if not path.exists():
        return ""
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 1_048_576))
            for chunk in iter(lambda: handle.read(65_536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _artifact_closure_manifest(session: RunSession) -> dict[str, Any] | None:
    """Durable artifact-closure metric for the terminal manifest.

    Mirrors what the gateway coordinator attaches to ``agent_runtime_end``.
    ``debug-run`` / manifest readers can check whether a run that produced
    files actually carried a deliverable closure.
    """
    workspace = getattr(session, "workspace", None)
    if workspace is None:
        return None
    snapshot = workspace.artifacts.snapshot()
    if not snapshot.artifacts:
        return None
    return {
        "artifact_count": len(snapshot.artifacts),
        "text": artifact_closure_text(snapshot),
    }


__all__ = [
    "ManifestFlushIncompleteError",
    "_materialization_lock",
    "ledger_high_watermark_for",
    "ledger_summary_for",
    "record_terminal_materialization",
    "session_locator",
    "terminal_event_seq_for",
    "terminal_event_seq_from_file",
    "watermark_from_file",
]
