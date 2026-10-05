"""Tests verifying the consolidated architecture of read/runs modules (INV-ARCH-14)."""

from __future__ import annotations

from pathlib import Path

from lca.plugins.transport.webserver.read.runs.evidence import (
    RunEvidenceReader,
    format_user_error,
    load_exception_records,
    sanitize_error,
)
from lca.plugins.transport.webserver.read.runs.identity import (
    AgentRef,
    default_agent_ref,
    parse_agent_ref,
)
from lca.plugins.transport.webserver.read.runs.live import (
    ProcessJournalBinding,
    flush_step_tree_artifacts,
    journal_outcome_from_session,
    stream_chat_completion,
)
from lca.plugins.transport.webserver.read.runs.terminal import (
    ManifestFlushIncompleteError,
    RegistryRunQueries,
    materialize_terminal_manifest,
    record_terminal_materialization,
)


def test_inv_arch_14_flat_module_exports() -> None:
    """INV-ARCH-14: Flat modules export expected public symbols."""
    # Identity
    ref = parse_agent_ref({"id": "custom", "name": "Custom Agent"})
    assert isinstance(ref, AgentRef)
    assert ref.agent_id == "custom"
    assert default_agent_ref().agent_id == "solo"

    # Evidence & Error presentation
    assert sanitize_error("TimeoutError: timeout exceeded") == "网络连接异常，请检查网络后重试"
    assert format_user_error("ValueError: invalid param", run_id="r1", trace_id="t1") == "invalid param"
    assert callable(load_exception_records)
    assert callable(RunEvidenceReader)

    # Live & Step flush & Process binding
    assert callable(flush_step_tree_artifacts)
    assert callable(journal_outcome_from_session)
    assert callable(stream_chat_completion)
    binding = ProcessJournalBinding()
    assert binding.subscriber_count == 0

    # Terminal materialization & Registry queries
    assert issubclass(ManifestFlushIncompleteError, RuntimeError)
    assert callable(record_terminal_materialization)
    assert callable(materialize_terminal_manifest)
    assert callable(RegistryRunQueries)


def test_inv_arch_14_no_micro_directories_remain() -> None:
    """INV-ARCH-14: read/runs contains no residual micro-directories."""
    read_runs_dir = Path("lca/plugins/transport/webserver/read/runs")
    assert read_runs_dir.is_dir()

    subdirs = [p.name for p in read_runs_dir.iterdir() if p.is_dir() and p.name != "__pycache__"]
    assert subdirs == [], f"Found residual micro-directories in read/runs: {subdirs}"
