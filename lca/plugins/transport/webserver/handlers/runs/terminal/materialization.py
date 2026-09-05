"""Materialize a terminal run manifest from Journal-owned facts."""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from pathlib import Path

import structlog

from lca.contracts.observability.run_locator import RunLocator
from lca.contracts.observability.run_manifest import RunManifest
from lca.infrastructure.atomic_write import atomic_write_text
from lca.infrastructure.observability.journal.engine.journal_io import (
    load_journal_records,
    record_normalize,
)
from lca.plugins.transport.webserver.handlers.runs.doctor import diagnose
from lca.plugins.transport.webserver.handlers.runs.observability.step_tree_flush import (
    flush_step_tree_artifacts,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession
from lca.plugins.transport.webserver.handlers.runs.terminal.status import journal_store

_TERMINAL_EVENT_TYPES = frozenset({"AgentRunFinished", "RunFinished", "RunSealed"})
_log = structlog.get_logger(__name__)


def record_terminal_materialization(session: RunSession) -> None:
    """Write a terminal manifest without owning facts.

    ADR-0164 Phase 7: 在写 manifest 之前 flush step-tree bundle(写
    journal.json + narrative.md)。 让 step-tree 是主存储, 旧 stream 是 raw。

    异常收口(per "工程思维:追问前提" 原则):
        任何 flush / diagnose / write_text 异常都不再静默吞掉 —
        全部收集到 ``extra.flush_errors``, 写进 manifest。 这样
        ``lca-ops debug-run <run_id>`` 一眼能看见哪一步、什么异常。
    """
    locator = session_locator(session)
    flush_errors: list[dict[str, str]] = []

    # ADR-0164: terminalize 时 step-tree flush(写 journal.json + narrative.md)
    flush_errors.extend(flush_step_tree_artifacts(session))

    try:
        # Prefer step-tree journal.json (main store) over legacy jsonl.
        report = diagnose(session, _doctor_journal_path(session, locator))
        if report.broken_hop or not report.factory["ok"]:
            _log.error(
                "run_doctor_verdict",
                hop=report.broken_hop or "factory",
                run_id=session.run_id,
                broken_hop=report.broken_hop,
                summary=report.summary,
            )
        manifest_path = locator.manifest_path(session.run_id)
        session_error = str(session.error or "")
        session_status = str(getattr(session.status, "value", session.status) or "")
        manifest = RunManifest(
            run_id=session.run_id,
            # ADR-0068 §决策二:plan_ref 顶层字段(declarative: compiled_run_plan_ref
            # 16-hex;solo: profile+mode+role fingerprint)。空串 = 未走 declarative plan。
            # ``RunSession.plan_ref`` 由 ``RunSessionBuilder._compute_plan_ref`` 在
            # build 阶段填好(PR 修复);此处不再 ``getattr`` 兜底,字段缺失应
            # fail-loud 而不是 silent 默认 ""(之前 diagnostics 也清理过同类兜底)。
            plan_ref=str(session.plan_ref),
            session_error=session_error,
            session_status=session_status,
            terminal_event_seq=terminal_event_seq_for(session),
            ledger_high_watermark=ledger_high_watermark_for(session),
            ledger_summary=ledger_summary_for(session),
            started_at=session.started_at,
            closed_at=session.closed_at if session.closed_at is not None else time.time(),
            extra={
                "doctor_report": report.as_dict(),
                "flush_errors": tuple(flush_errors),
                # COMPAT(owner: ADR-0165.1, from: extra.session_error,
                # delete_when: rg 'extra\\.session_error' traces/ scripts/ tests/ = 0,
                # forbidden_new_usage: 新 reader 读顶层 session_error/session_status)
                "session_error": session_error,
                "session_status": session_status,
            },
        )
        atomic_write_text(
            manifest_path,
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        )
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
    from lca.infrastructure.observability.backends.run_locator_fs import FilesystemRunLocator

    return FilesystemRunLocator(root=session.spine_path.parent.parent.parent)


def ledger_high_watermark_for(session: RunSession) -> int:
    """Read the final Journal sequence from memory, then fall back to the spine file."""
    store = journal_store(session.hub)
    if store is not None:
        try:
            events = store.events
            return max((int(getattr(event, "seq", 0) or 0) for event in events), default=0)
        except Exception as exc:
            _log.debug(
                "ledger_high_watermark_from_hub_failed", run_id=session.run_id, error=str(exc)
            )
    return watermark_from_file(session.spine_path)


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
    return terminal_event_seq_from_file(session.spine_path)


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


def ledger_summary_for(session: RunSession) -> str:
    """Hash the terminal one megabyte of the Journal for integrity navigation."""
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


__all__ = [
    "ledger_high_watermark_for",
    "ledger_summary_for",
    "record_terminal_materialization",
    "session_locator",
    "terminal_event_seq_for",
    "terminal_event_seq_from_file",
    "watermark_from_file",
]
