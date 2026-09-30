"""SafeExecutor — permission → validate → ToolStarted → cache → retry → execute → ToolInvoked.

ADR-0101 PR-2:tool 事件回归事实账本。``arguments`` / ``output`` 经
``EvidenceStore.prepare()`` 落到 evidence/<sha256>.json;``files`` 仍
作为 typed 字段(metadata-only,不截断)。

Split into cohesive modules:

- ``evidence``: pure observation → journal-field staging helpers.
- ``retry``: transient-vs-deterministic classification and backoff policy.
- ``executor``: ``SimpleSafeExecutor`` pipeline + journal commit helpers.
"""

from lca.cognition.body.executor.safe_executor.evidence import (
    _FILE_KEYS,
    _STDOUT_KEYS,
    _delta_summary_from_obs,
    _elapsed_ms,
    _extract_files_created,
    _extract_stderr,
    _extract_stdout_chars_total,
    _extract_stdout_head,
    _file_names,
)
from lca.cognition.body.executor.safe_executor.executor import (
    SimpleSafeExecutor,
    _commit_approval_requested,
    _commit_tool_denied,
    _commit_tool_invoked,
    _commit_tool_started,
    _resolve_evidence_pair,
)
from lca.cognition.body.executor.safe_executor.retry import (
    _DETERMINISTIC_EXCEPTIONS,
    classify_failure_kind,
    is_retryable_failure,
    next_backoff_delay,
)

__all__ = [
    "_DETERMINISTIC_EXCEPTIONS",
    "_FILE_KEYS",
    "_STDOUT_KEYS",
    "SimpleSafeExecutor",
    "_commit_approval_requested",
    "_commit_tool_denied",
    "_commit_tool_invoked",
    "_commit_tool_started",
    "_delta_summary_from_obs",
    "_elapsed_ms",
    "_extract_files_created",
    "_extract_stderr",
    "_extract_stdout_chars_total",
    "_extract_stdout_head",
    "_file_names",
    "_resolve_evidence_pair",
    "classify_failure_kind",
    "is_retryable_failure",
    "next_backoff_delay",
]
