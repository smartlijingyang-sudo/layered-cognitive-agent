"""Read-side run projections and queries for transport webserver.

Consolidated into four deep modules:
- identity: AgentRef data model and parsing
- evidence: evidence retrieval, failure summaries, and error sanitization
- live: live SSE streaming, process journal binding, and step tree flushing
- terminal: terminal manifest materialization, registry queries, and live tail compat
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
    sanitize_error,
)
from lca.plugins.transport.webserver.read.runs.identity import (
    DEFAULT_AGENT_ID,
    AgentRef,
    default_agent_ref,
    parse_agent_ref,
)
from lca.plugins.transport.webserver.read.runs.live import (
    ProcessJournalBinding,
    flush_step_tree_artifacts,
    iter_stamped_events,
    journal_outcome_from_session,
    stream_chat_completion,
    stream_process_journal_live,
)
from lca.plugins.transport.webserver.read.runs.terminal import (
    TEXT_CHANNEL_ALL,
    TEXT_CHANNEL_ANSWER,
    LiveGap,
    LiveTail,
    ManifestFlushIncompleteError,
    RegistryRunQueries,
    encode_live_gap,
    iter_live_sse,
    ledger_high_watermark_for,
    ledger_summary_for,
    materialize_terminal_manifest,
    record_terminal_materialization,
    session_locator,
    terminal_event_seq_for,
    watermark_from_file,
)

__all__ = [
    "DEFAULT_AGENT_ID",
    "TEXT_CHANNEL_ALL",
    "TEXT_CHANNEL_ANSWER",
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
    "materialize_terminal_manifest",
    "parse_agent_ref",
    "record_terminal_materialization",
    "sanitize_error",
    "session_locator",
    "stream_chat_completion",
    "stream_process_journal_live",
    "terminal_event_seq_for",
    "watermark_from_file",
]
