"""Materialize a terminal run manifest from Journal-owned facts and evidence blobs."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import structlog

from gateway.runs.doctor import diagnose
from gateway.runs.session import RunSession
from gateway.runs.terminal_status import journal_store
from lca.contracts.observability.run_locator import RunLocator
from lca.contracts.observability.run_manifest import IntegrityState, ManifestEvidence, RunManifest
from lca.infrastructure.observability.journal.journal_io import (
    load_journal_records,
    record_normalize,
)

_TERMINAL_EVENT_TYPES = frozenset({"AgentRunFinished", "RunFinished", "RunSealed"})
_log = structlog.get_logger(__name__)


def record_terminal_materialization(session: RunSession) -> None:
    """Write a terminal manifest and update its navigation pointer without owning facts."""
    locator = session_locator(session)
    try:
        report = diagnose(session, session.jsonl_path)
        if report.broken_hop or not report.factory["ok"]:
            _log.error(
                "run_doctor_verdict",
                hop=report.broken_hop or "factory",
                run_id=session.run_id,
                broken_hop=report.broken_hop,
                summary=report.summary,
            )
        manifest_path = locator.manifest_path(session.run_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = RunManifest(
            run_id=session.run_id,
            terminal_event_seq=terminal_event_seq_for(session),
            ledger_high_watermark=ledger_high_watermark_for(session),
            ledger_summary=ledger_summary_for(session),
            materializer_version=RunManifest.materializer_default_version(),
            evidence_integrity=evidence_integrity_for(locator, session.run_id),
            started_at=session.started_at,
            closed_at=session.closed_at if session.closed_at is not None else time.time(),
            extra={"doctor_report": report.as_dict()},
        )
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        locator.update_latest_pointer(session.run_id)
    except Exception:
        _log.warning(
            "run_terminal_materialization_failed",
            hop="H2",
            run_id=session.run_id,
            exc_info=True,
        )


def session_locator(session: RunSession) -> RunLocator:
    """Resolve the configured locator or derive a filesystem fallback for direct tests."""
    if session.locator is not None:
        return session.locator
    from lca.infrastructure.observability.run_locator_fs import FilesystemRunLocator

    return FilesystemRunLocator(root=session.jsonl_path.parent.parent.parent)


def ledger_high_watermark_for(session: RunSession) -> int:
    """Read the final Journal sequence from memory, then fall back to its JSONL file."""
    store = journal_store(session.hub)
    if store is not None:
        try:
            events = store.events
            return max((int(getattr(event, "seq", 0) or 0) for event in events), default=0)
        except Exception as exc:
            _log.debug(
                "ledger_high_watermark_from_hub_failed", run_id=session.run_id, error=str(exc)
            )
    return watermark_from_file(session.jsonl_path)


def terminal_event_seq_for(session: RunSession) -> int:
    """Return the seq of the last AgentRunFinished, RunFinished, or RunSealed event."""
    store = journal_store(session.hub)
    if store is not None:
        events: list[object] = []
        try:
            events = list(store.events)
        except Exception as exc:
            _log.debug("terminal_event_seq_from_hub_failed", run_id=session.run_id, error=str(exc))
        for stamped in reversed(events):
            event = getattr(stamped, "event", None)
            if event is not None and type(event).__name__ in _TERMINAL_EVENT_TYPES:
                return int(getattr(stamped, "seq", 0) or 0)
    return terminal_event_seq_from_file(session.jsonl_path)


def watermark_from_file(path: Path) -> int:
    """Scan the terminal JSONL watermark; empty or malformed rows are ignored."""
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
    """Scan JSONL in reverse for the last AgentRunFinished, RunFinished, or RunSealed seq."""
    if not path.exists():
        return 0
    try:
        records = load_journal_records(path, strict=False)
    except OSError:
        return 0
    for row in reversed(records):
        normalized = record_normalize(row)
        descriptor = normalized.get("descriptor", {}) or {}
        event_type = descriptor.get("type") or row.get("event_type")
        if event_type in _TERMINAL_EVENT_TYPES:
            return int(normalized.get("run_seq", row.get("seq", 0)) or 0)
    return 0


def evidence_integrity_for(locator: RunLocator, run_id: str) -> tuple[ManifestEvidence, ...]:
    """Project integrity facts for the run's materialized evidence blobs."""
    evidence_dir = locator.evidence_dir(run_id)
    if not evidence_dir.exists():
        return ()
    evidence: list[ManifestEvidence] = []
    for path in sorted(evidence_dir.iterdir()):
        if not path.is_file() or not path.name.startswith("sha256-"):
            continue
        digest = path.name.removeprefix("sha256-").split(".", 1)[0]
        if path.stat().st_size > 0:
            state, detail = IntegrityState.OK, ""
        else:
            state, detail = IntegrityState.MISSING, f"empty evidence blob: {path.name}"
        evidence.append(
            ManifestEvidence(ref_digest=digest, ref_algorithm="sha256", state=state, detail=detail)
        )
    return tuple(evidence)


def ledger_summary_for(session: RunSession) -> str:
    """Hash the terminal one megabyte of the Journal for integrity navigation."""
    path = session.jsonl_path
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


__all__ = [
    "evidence_integrity_for",
    "ledger_high_watermark_for",
    "ledger_summary_for",
    "record_terminal_materialization",
    "session_locator",
    "terminal_event_seq_for",
    "terminal_event_seq_from_file",
    "watermark_from_file",
]
