"""ADR-0164: think/act auto bridges at adapter/executor seams."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from lca.infrastructure.observability.facade import RunContext, bind
from lca.infrastructure.observability.journal.step.backend import StepGroupedBackend
from lca.plugins.seams.observability.run_ledger import _StepTreeBundle
from lca.runtime import step_lifecycle
from lca.runtime.journal_setup import BuildJournalMetadata, build_step_lifecycle_store
from lca.runtime.step_emitter import (
    bridge_act_closed,
    bridge_act_opened,
    bridge_llm_completed,
    bridge_think_closed,
    bridge_think_opened,
    bridge_tool_invoked,
    bridge_tool_started,
)


def _flush(store: step_lifecycle.StepLifecycleStore, path: Path) -> dict[str, Any]:
    backend = StepGroupedBackend(output_path=path, lifecycle_store=store)

    class _Narr:
        def write(self, document: object) -> None:
            del document

    _StepTreeBundle(backend=backend, narrative_writer=_Narr()).flush(outcome="completed")
    return json.loads(path.read_text())


def test_think_then_act_bridges_land_in_journal(tmp_path: Path) -> None:
    store = build_step_lifecycle_store(
        run_id="run_think_act",
        trace_id="trace_think_act",
        metadata=BuildJournalMetadata(
            agent_role="solo",
            strategy_key="solo",
            objective="write a joke",
        ),
    )
    token = step_lifecycle.set_lifecycle_store(store)
    try:
        with bind(RunContext(run_id="run_think_act", trace_id="trace_think_act")):
            bridge_think_opened(objective="write a joke")
            bridge_llm_completed(
                model="test-model",
                latency_ms=12,
                reasoning_preview="thinking…",
                decision="use_tool",
            )
            bridge_think_closed(outcome="ok", summary="use_tool")

            bridge_act_opened(objective="tool:run_python", tool_name="run_python")
            bridge_tool_started(
                tool_name="run_python",
                invocation_id="inv_1",
                arguments={"code": "print(1)"},
                arguments_summary="code=...",
            )
            bridge_tool_invoked(
                tool_name="run_python",
                invocation_id="inv_1",
                ok=True,
                latency_ms=5,
            )
            bridge_act_closed(outcome="ok")
    finally:
        step_lifecycle.reset_lifecycle_store(token)

    doc = _flush(store, tmp_path / "journal.json")
    phases = [s["phase"] for s in doc["steps"]]
    assert phases == ["think", "act"]
    assert doc["metadata"]["outcome"] == "completed"
    assert doc["steps"][0]["outcome"] == "ok"
    assert doc["steps"][1]["outcome"] == "ok"


@pytest.mark.asyncio
async def test_telemetry_adapter_opens_and_closes_think_step(tmp_path: Path) -> None:
    from lca.contracts.models.core.llm import LLMResponse
    from lca.infrastructure.observability.adapters.adapters import TelemetryLLMAdapter

    class _StubLLM:
        name = "stub"

        async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
            del kwargs
            return LLMResponse(text=f"echo:{prompt}", model="stub")

        async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[Any]:
            del prompt, kwargs
            if False:  # pragma: no cover
                yield None

    store = build_step_lifecycle_store(
        run_id="run_adapter_think",
        trace_id="trace_adapter_think",
        metadata=BuildJournalMetadata(
            agent_role="solo",
            strategy_key="solo",
            objective="hi",
        ),
    )
    token = step_lifecycle.set_lifecycle_store(store)
    try:
        adapter = TelemetryLLMAdapter(_StubLLM())  # type: ignore[arg-type]
        with bind(RunContext(run_id="run_adapter_think", trace_id="trace_adapter_think")):
            await adapter.complete("hello world")
    finally:
        step_lifecycle.reset_lifecycle_store(token)

    doc = _flush(store, tmp_path / "journal.json")
    assert [s["phase"] for s in doc["steps"]] == ["think"]
    assert doc["steps"][0]["outcome"] == "ok"
