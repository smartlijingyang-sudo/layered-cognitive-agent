"""ADR-0063 run-scoped diagnostics: contract, lifecycle, hook and CLI coverage."""

from __future__ import annotations

import json

import pytest
from cordis import Context
from typer.testing import CliRunner

from lca.contracts.atoms.enums import HookEvent
from lca.contracts.models.core.budget import Budget
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.diagnostic import DiagnosticCategory
from lca.contracts.models.observability.journal import RunScope
from lca.layer0_infra.observability import (
    AttributePolicy,
    JsonlDiagnosticSink,
    ObservabilityHub,
    bind,
    observe,
    observe_operation,
    run_scope,
)
from lca.layer0_infra.observability.policy import Verbosity
from lca.layer0_infra.ops.cli import app
from lca.layer1_cognitive.hook_registry import CordisHookRegistry


def _events(path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_diagnostic_event_is_run_scoped_and_redacted(tmp_path) -> None:
    path = tmp_path / "run.diagnostic.jsonl"
    hub = ObservabilityHub(
        diagnostic_sinks=(JsonlDiagnosticSink(path),),
        policy=AttributePolicy(Verbosity.STANDARD),
    )

    with bind(hub), run_scope(RunScope(run_id="run_123", trace_id="trace_456")):
        observe(
            DiagnosticCategory.LLM,
            "llm.complete",
            plugin="telemetry.llm",
            attributes={"prompt_preview": "api_key=sk-1234567890abcdef prompt"},
            output={"response_preview": "safe response"},
        )

    hub.release()
    [event] = _events(path)
    assert event["schema"] == "lca.diagnostic.v1"
    assert event["seq"] == 1
    assert event["run_id"] == "run_123"
    assert event["trace_id"] == "trace_456"
    assert event["category"] == "llm"
    assert "sk-1234567890abcdef" not in event["attributes"]["prompt_preview"]
    assert "[REDACTED]" in event["attributes"]["prompt_preview"]


def test_observe_operation_emits_started_and_terminal_status(tmp_path) -> None:
    path = tmp_path / "operation.diagnostic.jsonl"
    hub = ObservabilityHub(diagnostic_sinks=(JsonlDiagnosticSink(path),))

    with (
        bind(hub),
        run_scope(RunScope(run_id="run_123", trace_id="trace_456")),
        observe_operation(
            DiagnosticCategory.TOOL,
            "tool.execute",
            plugin="calculator",
            attributes={"tool_name": "calculator"},
        ) as operation,
    ):
        operation.set_output(result_preview="4")

    hub.release()
    started, completed = _events(path)
    assert started["status"] == "started"
    assert completed["status"] == "succeeded"
    assert completed["duration_ms"] is not None
    assert completed["output"] == {"result_preview": "4"}


@pytest.mark.asyncio
async def test_hook_trigger_uses_diagnostic_stream_not_stderr_logger(tmp_path) -> None:
    path = tmp_path / "hook.diagnostic.jsonl"
    hub = ObservabilityHub(diagnostic_sinks=(JsonlDiagnosticSink(path),))
    state = AgentState(trace_id="trace_456", task="test", budget=Budget(), step=3)

    with bind(hub), run_scope(RunScope(run_id="run_123", trace_id="trace_456")):
        hooks = CordisHookRegistry(Context())
        await hooks.trigger(HookEvent.PRE_THINK, state)

    hub.release()
    [event] = _events(path)
    assert event["category"] == "hook"
    assert event["operation"] == "hook.trigger"
    assert event["plugin"] == "hook_registry.simple"
    assert event["attributes"]["hook_event"] == HookEvent.PRE_THINK
    assert event["attributes"]["state_step"] == 3


def test_debug_trace_renders_and_filters_diagnostic_jsonl(tmp_path) -> None:
    path = tmp_path / "run.diagnostic.jsonl"
    path.write_text(
        "\n".join(
            (
                json.dumps(
                    {
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
