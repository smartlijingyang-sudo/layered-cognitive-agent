"""Merge strategy tests (ADR-0198)."""

from __future__ import annotations

from lca.contracts.models.observability.journal.step import ToolCallRecord, ToolResult
from lca_kernel.events.fold.merge import merge_dataclass, record_richness


def test_replace_richer_keeps_rich_tool_call() -> None:
    rich = ToolCallRecord(
        invocation_id="inv-1",
        name="executeCode",
        arguments={"code": "print(1)"},
        arguments_summary="code=...",
    )
    empty = ToolCallRecord(
        invocation_id="",
        name="",
        arguments={},
        arguments_summary="",
    )
    assert record_richness(rich) > record_richness(empty)
    merged = merge_dataclass(rich, empty, "replace_richer")
    assert merged.name == "executeCode"
    merged2 = merge_dataclass(empty, rich, "replace_richer")
    assert merged2.name == "executeCode"


def test_fill_empty_only_preserves_evidence() -> None:
    rich = ToolCallRecord(
        invocation_id="inv-1",
        name="executeCode",
        arguments={"code": "x"},
        arguments_summary="",
    )
    partial = ToolCallRecord(
        invocation_id="inv-1",
        name="",
        arguments={},
        arguments_summary="",
    )
    merged = merge_dataclass(rich, partial, "fill_empty_only")
    assert merged.name == "executeCode"
    assert merged.arguments == {"code": "x"}


def test_fill_empty_only_fills_missing() -> None:
    empty = ToolCallRecord(
        invocation_id="",
        name="",
        arguments={},
        arguments_summary="",
    )
    incoming = ToolCallRecord(
        invocation_id="inv-2",
        name="search",
        arguments={"q": "hi"},
        arguments_summary="q=hi",
    )
    merged = merge_dataclass(empty, incoming, "fill_empty_only")
    assert merged.name == "search"


def test_tool_result_span_does_not_wipe_stdout() -> None:
    rich = ToolResult(
        ok=True,
        latency_ms=100,
        stdout_head="hello world",
        stdout_chars_total=11,
        stdout_truncated=False,
        stderr="",
        files_created=(),
        error=None,
        delta_summary="ok",
    )
    empty = ToolResult(
        ok=True,
        latency_ms=0,
        stdout_head="",
        stdout_chars_total=0,
        stdout_truncated=False,
        stderr="",
        files_created=(),
        error=None,
        delta_summary="",
    )
    merged = merge_dataclass(rich, empty, "fill_empty_only")
    assert merged.stdout_head == "hello world"
    assert merged.stdout_chars_total == 11
