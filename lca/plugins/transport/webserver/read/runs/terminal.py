"""Materialize terminal run manifest from Journal-owned facts and provide registry queries.

Consolidates:
- Terminal manifest recording, integrity hashing, flock idempotency, and error collection
- Registry run queries and streaming
- Gateway live-tail backward compatibility facades
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import time
import traceback
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from lca.contracts.observability.canonical_digest import canonical_digest
from lca.contracts.observability.health.report import RunHealthSummary
from lca.contracts.observability.registry.run_locator import RunLocator
from lca.contracts.observability.registry.run_manifest import RunManifest
from lca.infrastructure.atomic.write import atomic_write_text
from lca.infrastructure.observability.journal.engine.journal_io import (
    load_journal_records,
    record_normalize,
)
from lca.infrastructure.observability.journal.stream.live_tail import (
    TEXT_CHANNEL_ALL,
    TEXT_CHANNEL_ANSWER,
    LiveGap,
    LiveTail,
    encode_live_gap,
    iter_live_sse,
)
from lca.infrastructure.workspace.artifact_ledger import artifact_closure_text
from lca.plugins.observability.health.run_health_fold import fold_run_health
from lca.plugins.transport.webserver.doctor import DoctorReport, diagnose

if TYPE_CHECKING:
    from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
        RunRegistry,
        RunSession,
    )
from lca.plugins.transport.webserver.read.runs.live import (
    flush_step_tree_artifacts,
)
from lca.plugins.transport.webserver.read.runs.live import (
    iter_stamped_events as _iter_stamped_events,
)
from lca.plugins.transport.webserver.read.runs.live import (
    stream_chat_completion as _stream_chat_completion,
)
from lca.plugins.transport.webserver.read.runs.live import (
    stream_process_journal_live as _stream_process_journal_live,
)

_log = structlog.get_logger(__name__)


# --- Terminal Manifest Materialization ---


class ManifestFlushIncompleteError(RuntimeError):
    """Raised when ``flush_step_tree_artifacts`` returns errors."""


@contextlib.contextmanager
def _materialization_lock(manifest_path: Path) -> Iterator[None]:
    """Per-run-id ``fcntl.flock`` around manifest close-path."""
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
    """Write a terminal manifest without owning facts."""
    locator = session_locator(session)
    flush_errors: list[dict[str, str]] = []

    flush_errors.extend(flush_step_artifacts_with_log(session))

    if flush_errors:
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
            payload_for_hash = health_report.model_dump(mode="json")
            payload_for_hash.pop("generated_at", None)
            health_hash = canonical_digest(payload_for_hash, length=64, prefix="")

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
                    return

            manifest = RunManifest(
                run_id=session.run_id,
                plan_ref=str(session.plan_ref),
                session_error=session_error,
                session_status=session_status,
                health_summary=health_summary,
                health_hash=health_hash,
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
        raise
    except Exception as exc:
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


materialize_terminal_manifest = record_terminal_materialization


def flush_step_artifacts_with_log(session: RunSession) -> list[dict[str, str]]:
    """Wrap ``flush_step_tree_artifacts`` to log any errors before returning."""
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
    """Read final Session sequence from spine file (SSOT only). @deprecated."""
    return watermark_from_file(session.spine_path)


def terminal_event_seq_for(session: RunSession) -> int:
    """Return seq of last terminal event. @deprecated."""
    return 0


def watermark_from_file(path: Path) -> int:
    """Scan terminal JSONL watermark. @deprecated."""
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
    """Scan JSONL in reverse for last terminal event seq. @deprecated."""
    return 0


def ledger_summary_for(session: RunSession) -> str:
    """Hash the terminal one megabyte of Journal for integrity navigation. @deprecated."""
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


# --- Registry Run Queries ---


class RegistryRunQueries:
    """Own read-only run projections and process-level observability streams."""

    def __init__(self, registry: RunRegistry) -> None:
        self._registry = registry

    async def summary(self, run_id: str) -> dict[str, Any] | None:
        self._registry.prune()
        return self._registry.summary(run_id)

    async def stream_chat_completion(self, run_id: str, last_seq: int = 0) -> AsyncIterator[bytes]:
        """Stream a run's journal events encoded as OpenAI ChatCompletion chunks."""
        session = self._registry.get(run_id)
        if session is None:
            return
        async for line in _stream_chat_completion(session, last_seq=last_seq):
            yield line

    async def iter_stamped_events(self, run_id: str, after_seq: int = 0) -> AsyncIterator[Any]:
        """Yield the raw ``StampedEvent`` stream for one run."""
        session = self._registry.get(run_id)
        if session is None:
            return
        async for item in _iter_stamped_events(session, after_seq=after_seq):
            yield item

    async def doctor(self, run_id: str) -> DoctorReport | None:
        session = self._registry.get(run_id)
        spine_path = (
            session.spine_path if session is not None else self._registry.spine_path_for(run_id)
        )
        if session is None and not spine_path.is_file():
            return None
        target_path = spine_path
        locator = getattr(session, "locator", None) if session is not None else None
        if locator is not None:
            step_path = locator.journal_step_path(run_id)
            if step_path.exists():
                target_path = step_path
        else:
            step_path = spine_path.parent / "journal.json"
            if step_path.exists():
                target_path = step_path
        return diagnose(session, target_path)

    def journal_path(self, run_id: str) -> Path | None:
        """Return only the current run's spine path; never fall back across sessions."""
        path = self._registry.spine_path_for(run_id)
        return path if path.is_file() else None

    def latest_bindings(self) -> object | None:
        """Expose the context projection without exposing the Registry itself."""
        return self._registry.latest_bindings()

    def status_counts(self) -> dict[str, int]:
        return self._registry.status_counts()

    def live_totals(self) -> dict[str, int]:
        return self._registry.live_totals()

    def stream_process_journal_live(self, last_seq: int = 0) -> AsyncIterator[bytes]:
        """Provide the process-level Journal stream for operations endpoints."""
        return _stream_process_journal_live(
            self._registry.journal.tail,
            last_seq=last_seq,
        )


__all__ = [
    "TEXT_CHANNEL_ALL",
    "TEXT_CHANNEL_ANSWER",
    "LiveGap",
    "LiveTail",
    "ManifestFlushIncompleteError",
    "RegistryRunQueries",
    "_materialization_lock",
    "encode_live_gap",
    "flush_step_artifacts_with_log",
    "iter_live_sse",
    "ledger_high_watermark_for",
    "ledger_summary_for",
    "materialize_terminal_manifest",
    "record_terminal_materialization",
    "session_locator",
    "terminal_event_seq_for",
    "terminal_event_seq_from_file",
    "watermark_from_file",
]
