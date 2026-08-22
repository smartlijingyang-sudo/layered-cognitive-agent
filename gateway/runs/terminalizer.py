"""Terminalize one gateway run with one ordered, testable operation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import structlog

from gateway.runs.doctor import diagnose
from gateway.runs.session import RunRegistry, RunSession, RunStatus
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.observability.run_locator import RunLocator
from lca.contracts.observability.run_manifest import IntegrityState, ManifestEvidence, RunManifest
from lca.layer0_infra.observability import (
    BoundObservability,
    fold_run_state,
)
from lca.layer0_infra.observability.journal.reducer import RunStatus as JournalRunStatus
from lca.layer0_infra.tools.run_finalizer import finalize_run

_EXPORT_DISPOSE_TIMEOUT_S = 3.0
_TERMINAL_EVENT_TYPES = frozenset({"AgentRunFinished", "RunFinished", "RunSealed"})
_log = structlog.get_logger(__name__)


class RunTerminalizer:
    """Own the ordered transition from an active run to a terminal materialization.

    ``terminalize`` is the only interface for the execution and resume paths.
    It keeps artifact closure, journal-derived status, registry cleanup,
    manifest materialization, and buffered exporter shutdown in one place.
    """

    def __init__(
        self,
        registry: RunRegistry,
        *,
        finalizer: Callable[[str], Awaitable[None]] = finalize_run,
        materializer: Callable[[RunSession], None] | None = None,
    ) -> None:
        self._registry = registry
        self._finalizer = finalizer
        self._materializer = materializer or _record_terminal_materialization

    async def terminalize(self, session: RunSession, *, workspace: Any, success: bool) -> None:
        """Close a run exactly once while preserving journal ownership of status."""

        try:
            if session.hub is not None:
                _emit_artifact_closure_if_needed(workspace, session, session.hub)
            await self._finalizer(session.run_id)
        except Exception:
            _log.exception("finalize_run_pre_close_failed", hop="H2", run_id=session.run_id)
        finally:
            try:
                if session.hub is not None:
                    session.hub.close()
            finally:
                _derive_terminal_status(session, success)
                self._registry.clear_inflight(session.run_id)
                self._registry.prune()
                self._materializer(session)
                if session.hub is not None:
                    await _dispose_export(session.hub)


async def _dispose_export(hub: BoundObservability) -> None:
    """Flush Langfuse or OTel exporters outside the event loop."""

    try:
        await asyncio.wait_for(asyncio.to_thread(hub.flush), timeout=_EXPORT_DISPOSE_TIMEOUT_S)
    except TimeoutError:
        _log.warning("observability_export_flush_timeout", hop="H3")
    except Exception:
        _log.warning("observability_export_flush_failed", hop="H3", exc_info=True)


def _journal_store(hub: BoundObservability | None) -> Any:
    """Extract the run store from a bound journal, if one is present."""

    if hub is None or hub.journal is None:
        return None
    return getattr(hub.journal, "store", hub.journal)


def _derive_terminal_status(session: RunSession, success: bool) -> None:
    """Derive terminal status from journal facts, then apply session signals."""

    if session.cancel_requested:
        session.status = RunStatus.CANCELED
    elif session.error:
        session.status = RunStatus.FAILED
    elif session.hub is not None:
        store = _journal_store(session.hub)
        if store is None:
            _fallback_terminal_status(session, success)
        else:
            derived = fold_run_state(store.events)
            session.status = _journal_to_session_status(derived.status)
    else:
        _fallback_terminal_status(session, success)
    if session.status in {RunStatus.CANCELED, RunStatus.FAILED, RunStatus.COMPLETED}:
        session.closed_at = time.time()


def _journal_to_session_status(journal_status: JournalRunStatus | None) -> RunStatus:
    """Map the journal reducer status into the carrier session status."""

    mapping: dict[JournalRunStatus, RunStatus] = {
        JournalRunStatus.COMPLETED: RunStatus.COMPLETED,
        JournalRunStatus.FAILED: RunStatus.FAILED,
        JournalRunStatus.CANCELED: RunStatus.CANCELED,
        JournalRunStatus.RUNNING: RunStatus.COMPLETED,
        JournalRunStatus.WAITING_INPUT: RunStatus.WAITING_INPUT,
    }
    if journal_status is None:
        return RunStatus.COMPLETED
    return mapping.get(journal_status, RunStatus.COMPLETED)


def _fallback_terminal_status(session: RunSession, success: bool) -> None:
    """Retain the carrier fallback when no journal is available."""

    if session.error:
        session.status = RunStatus.FAILED
    elif success:
        session.status = RunStatus.COMPLETED


def _record_terminal_materialization(session: RunSession) -> None:
    """Write the terminal manifest and update the navigation pointer.

    The manifest is a materialization rather than a fact owner.  Journal facts
    remain the source for replay and terminal status derivation.
    """

    locator = _session_locator(session)
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
            terminal_event_id=_terminal_event_id_for(session),
            ledger_high_watermark=_ledger_high_watermark_for(session),
            ledger_summary=_ledger_summary_for(session),
            materializer_version=RunManifest.materializer_default_version(),
            evidence_integrity=_evidence_integrity_for(locator, session.run_id),
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
            "run_terminal_materialization_failed", hop="H2", run_id=session.run_id, exc_info=True
        )


def _session_locator(session: RunSession) -> RunLocator:
    """Resolve the run locator, deriving a filesystem fallback for direct tests."""

    if session.locator is not None:
        return session.locator
    from lca.layer0_infra.observability.run_locator_fs import FilesystemRunLocator

    return FilesystemRunLocator(root=session.jsonl_path.parent.parent.parent)


def _ledger_high_watermark_for(session: RunSession) -> int:
    """Read the final journal sequence from memory, then fall back to JSONL."""

    store = _journal_store(session.hub)
    if store is not None:
        try:
            events = store.events  # type: ignore[attr-defined]
            return max((int(getattr(event, "seq", 0) or 0) for event in events), default=0)
        except Exception as exc:
            _log.debug(
                "ledger_high_watermark_from_hub_failed", run_id=session.run_id, error=str(exc)
            )
    return _watermark_from_file(session.jsonl_path)


def _terminal_event_id_for(session: RunSession) -> str:
    """Return the final AgentRunFinished, RunFinished, or RunSealed event id."""

    store = _journal_store(session.hub)
    if store is not None:
        events: list[object] = []
        try:
            events = list(store.events)  # type: ignore[attr-defined]
        except Exception as exc:
            _log.debug("terminal_event_id_from_hub_failed", run_id=session.run_id, error=str(exc))
        for stamped in reversed(events):
            event = getattr(stamped, "event", None)
            if event is not None and type(event).__name__ in _TERMINAL_EVENT_TYPES:
                return str(getattr(stamped, "event_id", "") or "")
    return _terminal_event_id_from_file(session.jsonl_path)


def _watermark_from_file(path: Path) -> int:
    """Scan the terminal JSONL watermark; empty or malformed rows are ignored."""

    if not path.exists():
        return 0
    last = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                last = max(last, int(row.get("seq", 0) or 0))
    except OSError:
        return 0
    return last


def _terminal_event_id_from_file(path: Path) -> str:
    """Scan JSONL for the last AgentRunFinished event id."""

    if not path.exists():
        return ""
    last = ""
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("event_type") in _TERMINAL_EVENT_TYPES:
                    last = str(row.get("event_id") or row.get("scope", {}).get("event_id") or "")
    except OSError:
        return ""
    return last


def _evidence_integrity_for(locator: RunLocator, run_id: str) -> tuple[ManifestEvidence, ...]:
    """Record integrity for materialized evidence blobs."""

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


def _ledger_summary_for(session: RunSession) -> str:
    """Hash the terminal one megabyte of the journal for integrity navigation."""

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


def _emit_artifact_closure_if_needed(
    workspace: Any,
    session: RunSession,
    hub: BoundObservability,
) -> None:
    """Append the workspace artifact closure before the journal is closed."""

    if workspace is None:
        return
    artifacts = workspace.artifacts.snapshot().artifacts
    if not artifacts:
        return
    closure = workspace.artifacts.closure_text()
    if not closure:
        return
    from lca.contracts.models.observability.journal import StepTextDelta

    try:
        store = _journal_store(hub)
        if store is not None:
            store.append(
                StepTextDelta(
                    step=-1,
                    text_delta="\n\n" + closure,
                    seq=0,
                    channel=StreamChannel.ANSWER.value,
                )
            )
        _log.info(
            "artifact_closure_emitted",
            hop="H2",
            run_id=session.run_id,
            artifact_count=len(artifacts),
            status=session.status.value,
        )
    except Exception:
        _log.warning("artifact_closure_emit_failed", hop="H2", run_id=session.run_id, exc_info=True)


__all__ = ["RunTerminalizer"]
