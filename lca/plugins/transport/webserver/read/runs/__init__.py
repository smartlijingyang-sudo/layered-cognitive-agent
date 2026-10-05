"""Read-side run projections (ADR-0195 §2.4 observe plane).

Consolidated into deep flat modules (INV-ARCH-14):
- ``identity``: session identity retrieval and metadata
- ``evidence``: evidence extraction, failure diagnostics, formatted presentation
- ``live``: active run streams, step-tree refresh, journal projection binding
- ``terminal``: terminal-state materialization and terminal lifecycle queries
"""

from __future__ import annotations

from lca.plugins.transport.webserver.read.runs.evidence import (
    EvidencePayloadDecodeError,
    InvalidEvidenceDigestError,
    RunEvidence,
    RunEvidenceNotFoundError,
    RunEvidenceQueryError,
    RunEvidenceReader,
    failure_summary_for_run,
    format_user_error,
    load_exception_records,
    normalize_evidence_digest,
    sanitize_error,
)
from lca.plugins.transport.webserver.read.runs.identity import (
    DEFAULT_AGENT_ID,
    AgentRef,
    default_agent_ref,
    parse_agent_ref,
)
from lca.plugins.transport.webserver.read.runs.live import (
    TEXT_CHANNEL_ALL,
    TEXT_CHANNEL_ANSWER,
    LiveGap,
    LiveTail,
    ProcessJournalBinding,
    encode_live_gap,
    flush_step_tree_artifacts,
    iter_live_sse,
    iter_stamped_events,
    journal_outcome_from_session,
    stream_chat_completion,
    stream_process_journal_live,
    stream_run_fold,
)
from lca.plugins.transport.webserver.read.runs.terminal import (
    ManifestFlushIncompleteError,
    RegistryRunQueries,
    ledger_high_watermark_for,
    ledger_summary_for,
    record_terminal_materialization,
    session_locator,
    terminal_event_seq_for,
    terminal_event_seq_from_file,
    watermark_from_file,
)

__all__ = [
    "DEFAULT_AGENT_ID",
    "AgentRef",
    "EvidencePayloadDecodeError",
    "InvalidEvidenceDigestError",
    "LiveGap",
    "LiveTail",
    "ManifestFlushIncompleteError",
    "ProcessJournalBinding",
    "RegistryRunQueries",
    "RunEvidence",
    "RunEvidenceNotFoundError",
    "RunEvidenceQueryError",
    "RunEvidenceReader",
    "TEXT_CHANNEL_ALL",
    "TEXT_CHANNEL_ANSWER",
    "default_agent_ref",
    "encode_live_gap",
    "failure_summary_for_run",
    "flush_step_tree_artifacts",
    "format_user_error",
    "iter_live_sse",
    "iter_stamped_events",
    "journal_outcome_from_session",
    "ledger_high_watermark_for",
    "ledger_summary_for",
    "load_exception_records",
    "normalize_evidence_digest",
    "parse_agent_ref",
    "record_terminal_materialization",
    "sanitize_error",
    "session_locator",
    "stream_chat_completion",
    "stream_process_journal_live",
    "stream_run_fold",
    "terminal_event_seq_for",
    "terminal_event_seq_from_file",
    "watermark_from_file",
]