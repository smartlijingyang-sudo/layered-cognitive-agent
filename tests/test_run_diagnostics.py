"""ADR-0063 run-scoped diagnostics: contract, lifecycle, hook and CLI coverage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cordis import Context
from typer.testing import CliRunner

from lca.contracts.atoms.enums import HookEvent
from lca.contracts.models.core.budget import Budget
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.diagnostic import DiagnosticCategory
from lca.contracts.models.observability.journal import RunScope
from lca.infrastructure.observability import (
    bind_backends,
    record_operation,
    record_runtime,
    run_scope,
)
from lca.infrastructure.observability.facade import RunContext, bind
from lca.infrastructure.observability.journal.journal_io import load_journal_records
from lca.infrastructure.observability.journal.jsonl_projector import JsonlJournalProjector
from lca.infrastructure.observability.policy import Verbosity
from lca.infrastructure.ops.cli import app
from lca.cognition.hook_registry import CordisHookRegistry
from tests.support.observability_helpers import RuntimeCategoryFilter, make_test_bound


def _events(path: Path) -> list[dict[str, object]]:
    return load_journal_records(path)


def test_diagnostic_event_is_run_scoped_and_redacted(tmp_path: Path) -> None:
    """RuntimeObserved carrying a secret preview is redacted at journal commit."""
    path = tmp_path / "run.diagnostic.jsonl"
    projector = JsonlJournalProjector(path)
    bound = make_test_bound(
        verbosity=Verbosity.STANDARD,
        projections=[RuntimeCategoryFilter(DiagnosticCategory.LLM, projector)],
    )

    with (
        bind_backends(bound),
        bind(RunContext()),
        run_scope(RunScope(run_id="run_123", trace_id="trace_456")),
    ):
        record_runtime(
            DiagnosticCategory.LLM,
            "llm.complete",
            plugin="telemetry.llm",
            attributes={"prompt_preview": "api_key=sk-1234567890abcdef prompt"},
            output={"response_preview": "safe response"},
        )

    bound.journal.flush()  # type: ignore[union-attr]
    bound.journal.close()  # type: ignore[union-attr]
    [event] = _events(path)
    # ADR-0065 §三 / PR-3: v2 envelope
    assert event["schema"] == "lca.journal/2"
    assert event["scope"]["run_id"] == "run_123"
    assert event["scope"]["trace_id"] == "trace_456"
    # ADR-0101 PR-2:view-only stripping 已移除(0065 §四);RuntimeObserved
    # attributes / output 子字典不再剥离 prompt_preview / response_preview
    # 等 view-only 键,新策略由 frontend 渲染层处理(白名单)。
    assert "prompt_preview" in event["data"].get("attributes", {})
    assert "response_preview" in event["data"].get("output", {})


def test_observe_operation_emits_started_and_terminal_status(tmp_path: Path) -> None:
    """``record_operation`` writes STARTED on enter and SUCCEEDED on exit."""
    path = tmp_path / "operation.diagnostic.jsonl"
    projector = JsonlJournalProjector(path)
    bound = make_test_bound(
        projections=[RuntimeCategoryFilter(DiagnosticCategory.TOOL, projector)],
    )

    with (
        bind_backends(bound),
        bind(RunContext()),
        run_scope(RunScope(run_id="run_123", trace_id="trace_456")),
        record_operation(
            DiagnosticCategory.TOOL,
            "tool.execute",
            plugin="calculator",
            attributes={"tool_name": "calculator"},
        ) as operation,
    ):
        operation.set_output(result_preview="4")

    bound.journal.flush()  # type: ignore[union-attr]
    bound.journal.close()  # type: ignore[union-attr]
    started, completed = _events(path)
    assert started["data"]["outcome"] == "started"
    assert completed["data"]["outcome"] == "ok"
    # ADR-0101 PR-2:view-only stripping 已移除;RuntimeObserved output
    # 子字典保留 result_preview 等键(语义:诊断元数据,非渲染细节)。
    assert "result_preview" in completed["data"]["output"]
    assert "duration_ms" in completed["data"]["output"]


@pytest.mark.asyncio
async def test_hook_trigger_uses_diagnostic_stream_not_stderr_logger(tmp_path: Path) -> None:
    """PRE_THINK hook triggers a RuntimeObserved that flows to the journal."""
    path = tmp_path / "hook.diagnostic.jsonl"
    projector = JsonlJournalProjector(path)
    bound = make_test_bound(
        projections=[RuntimeCategoryFilter(DiagnosticCategory.HOOK, projector)],
    )
    state = AgentState(trace_id="trace_456", task="test", budget=Budget(), step=3)

    with (
        bind_backends(bound),
        bind(RunContext()),
        run_scope(RunScope(run_id="run_123", trace_id="trace_456")),
    ):
        hooks = CordisHookRegistry(Context())
        await hooks.trigger(HookEvent.PRE_THINK, state)

    bound.journal.flush()  # type: ignore[union-attr]
    bound.journal.close()  # type: ignore[union-attr]
    [event] = _events(path)
    payload = event["data"]
    assert payload["operation"] == "hook.trigger"
    assert payload["source"] == "hook_registry.simple"
    assert payload["attributes"]["hook_event"] == HookEvent.PRE_THINK.value
    assert payload["attributes"]["state_step"] == 3


def test_debug_trace_renders_and_filters_diagnostic_jsonl(tmp_path: Path) -> None:
    """CLI ``debug trace`` accepts a diagnostic-shaped JSONL and filters by category."""
    path = tmp_path / "run.diagnostic.jsonl"
    path.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "schema": "lca.diagnostic.v1",
                        "ts": 1.0,
                        "category": "llm",
                        "status": "succeeded",
                        "plugin": "telemetry.llm",
                        "operation": "llm.complete",
                        "duration_ms": 12,
                        "attributes": {"model": "mock"},
                        "output": {"completion_tokens": 3},
                    }
                ),
                json.dumps(
                    {
                        "schema": "lca.diagnostic.v1",
                        "ts": 2.0,
                        "category": "tool",
                        "status": "succeeded",
                        "plugin": "calculator",
                        "operation": "tool.complete",
                        "duration_ms": 2,
                        "attributes": {},
                        "output": {},
                    }
                ),
            )
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["debug", "trace", "--diagnostic", str(path), "--category", "llm"],
    )
    assert result.exit_code == 0
    assert "llm.complete" in result.output
    assert "telemetry.llm" in result.output
    assert "tool.complete" not in result.output


_ = Any  # silence unused-import warnings for typing imports kept for readability
