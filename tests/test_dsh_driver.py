"""DSH compare driver — mapping, projection, and execute branch."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    JournalEvent,
    LlmCallStarted,
    ReasoningDelta,
    StepTextDelta,
    ToolInvoked,
    ToolStarted,
)
from lca.contracts.protocols import DshRuntime
from lca.layer0_infra.dsh.driver import DshTurnDriver, DshTurnSpec
from lca.layer0_infra.dsh.mapping import map_dsh_tool
from lca.layer0_infra.dsh.models import DshNotification, DshTurnResult
from lca.layer0_infra.dsh.projector import DshJournalProjector
from lca.layer0_infra.dsh.routing import is_dsh_driver


class _Sink:
    def __init__(self) -> None:
        self.events: list[JournalEvent] = []

    def emit(self, event: JournalEvent) -> None:
        self.events.append(event)


class _Archive:
    def __init__(self) -> None:
        self.rows: list[DshNotification] = []

    def append(self, notification: DshNotification) -> None:
        self.rows.append(notification)


class _FakeRuntime:
    def __init__(self, notifications: list[DshNotification], result: DshTurnResult) -> None:
        self._notifications = notifications
        self._result = result
        self.seen: DshTurnSpec | None = None

    def run_turn(self, spec: DshTurnSpec, on_event: object) -> DshTurnResult:
        self.seen = spec
        callback = on_event
        for item in self._notifications:
            callback(item)  # type: ignore[operator]
        return self._result


def _session_event(event_type: str, data: dict | None = None) -> DshNotification:
    return DshNotification(
        method="session.event",
        payload={"sessionId": "s1", "event": {"type": event_type, "data": data or {}}},
    )


def test_settings_follow_lca_qwen_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from lca.layer0_infra.dsh.settings import DshSettings

    monkeypatch.setenv("LLM_MODEL", "qwen3.7-plus")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_MAX_TOKENS", "4096")
    from lca.layer0_infra.llm_adapter.settings import clear_llm_settings_cache

    clear_llm_settings_cache()
    settings = DshSettings()
    assert settings.resolved_model() == "qwen3.7-plus"
    assert settings.resolved_api_key() == "sk-test"
    assert settings.resolved_base_url() == "https://example.test/v1"
    assert settings.resolved_max_tokens() == 4096


def test_is_dsh_driver_only_for_dsh_token() -> None:
    assert is_dsh_driver("dsh")
    assert is_dsh_driver("DSH")
    assert not is_dsh_driver("device")
    assert not is_dsh_driver("sandbox")
    assert not is_dsh_driver("")


def test_map_dsh_tools_to_local_wire_names() -> None:
    assert map_dsh_tool("bash") == "local_runCommand"
    assert map_dsh_tool("read") == "local_readFile"
    assert map_dsh_tool("write") == "local_writeFile"
    assert map_dsh_tool("edit") == "local_editFile"
    assert map_dsh_tool("todo_write") == "todo_write"


def test_projector_maps_reasoning_text_and_bash() -> None:
    sink = _Sink()
    projector = DshJournalProjector(sink)
    projector.feed(_session_event("turn/start", {"turn": 1}))
    projector.feed(_session_event("step/start", {"turn": 1, "step": 1}))
    projector.feed(
        _session_event(
            "assistant/chunk",
            {"turn": 1, "step": 1, "chunk": {"type": "reasoning-delta", "text": "think"}},
        )
    )
    projector.feed(
        _session_event(
            "assistant/chunk",
            {"turn": 1, "step": 1, "chunk": {"type": "text-delta", "text": "hi"}},
        )
    )
    projector.feed(
        _session_event(
            "tool/call",
            {
                "turn": 1,
                "step": 1,
                "callId": "c1",
                "name": "bash",
                "arguments": '{"command": "echo hi", "description": "say hi"}',
            },
        )
    )
    projector.feed(
        _session_event(
            "tool/result",
            {
                "turn": 1,
                "step": 1,
                "message": {
                    "content": [
                        {
                            "type": "tool-result",
                            "toolCallId": "c1",
                            "isError": False,
                            "content": [{"type": "text", "text": "hi\n"}],
                        }
                    ]
                },
            },
        )
    )
    projector.feed(_session_event("turn/end", {"turn": 1, "reason": {"kind": "completed"}}))

    kinds = [type(event).__name__ for event in sink.events]
    assert kinds[0] == "LlmCallStarted"
    assert any(
        isinstance(event, ReasoningDelta) and event.text_delta == "think" for event in sink.events
    )
    assert any(
        isinstance(event, StepTextDelta) and event.text_delta == "hi" and event.channel == "answer"
        for event in sink.events
    )
    started = next(event for event in sink.events if isinstance(event, ToolStarted))
    assert started.tool_name == "local_runCommand"
    assert started.invocation_id == "c1"
    assert started.plugin_state["command"] == "echo hi"
    assert started.plugin_state["executionEnv"] == "local"
    invoked = next(event for event in sink.events if isinstance(event, ToolInvoked))
    assert invoked.ok is True
    assert invoked.plugin_state["stdout"] == "hi\n"
    assert any(
        isinstance(event, AgentRunFinished) and event.status == "completed" for event in sink.events
    )


def test_driver_archives_raw_and_projects(tmp_path: Path) -> None:
    notes = [
        _session_event("turn/start", {"turn": 1}),
        _session_event(
            "assistant/chunk",
            {"turn": 1, "step": 1, "chunk": {"type": "text-delta", "text": "done"}},
        ),
        _session_event("turn/end", {"turn": 1, "reason": {"kind": "completed"}}),
    ]
    runtime = _FakeRuntime(
        notes,
        DshTurnResult(session_id="s1", final_response="done", finish_reason="completed"),
    )
    sink = _Sink()
    archive = _Archive()
    driver = DshTurnDriver(runtime=runtime, projector=DshJournalProjector(sink), archive=archive)
    spec = DshTurnSpec(
        prompt="list files", session_id="s1", cwd=str(tmp_path), session_root=str(tmp_path)
    )
    result = driver.run(spec)
    assert result.final_response == "done"
    assert runtime.seen == spec
    assert len(archive.rows) == 3
    assert any(isinstance(event, LlmCallStarted) for event in sink.events)
    assert any(isinstance(event, AgentRunFinished) for event in sink.events)


@pytest.mark.asyncio
async def test_execute_run_uses_dsh_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway.runs.execute import create_run_session, execute_run
    from gateway.runs.session import RunRegistry, RunStatus

    monkeypatch.setenv("LCA_OBS_INCLUDE_LANGFUSE", "false")
    monkeypatch.setenv("LCA_OBS_BACKENDS", "console")

    notes = [
        _session_event("turn/start", {"turn": 1}),
        _session_event(
            "assistant/chunk",
            {"turn": 1, "step": 1, "chunk": {"type": "text-delta", "text": "ok"}},
        ),
        _session_event("turn/end", {"turn": 1, "reason": {"kind": "completed"}}),
    ]
    fake = _FakeRuntime(
        notes,
        DshTurnResult(session_id="s1", final_response="ok", finish_reason="completed"),
    )

    def _runtime(_settings: object) -> DshRuntime:
        return fake  # type: ignore[return-value]

    monkeypatch.setenv("DSH_CWD", str(tmp_path))
    monkeypatch.setattr("gateway.runs.dsh_execute.default_runtime", _runtime)
    monkeypatch.setattr(
        "gateway.runs.execute._freeze_bindings",
        lambda session: type("B", (), {"primary": None, "secondary": None})(),
    )

    registry = RunRegistry(runs_dir=tmp_path)
    session = create_run_session(
        registry,
        question="hello",
        user_text="hello",
        mode="solo",
        execution_target="dsh",
    )
    await execute_run(registry, run_id=session.run_id, question=session.question, mode="solo")
    assert session.status == RunStatus.COMPLETED
    assert fake.seen is not None
    assert fake.seen.prompt == "hello"
    archive = tmp_path / f"{session.run_id}.dsh.jsonl"
    assert archive.is_file()
    assert archive.read_text(encoding="utf-8").count("session.event") == 3
    journal = session.jsonl_path.read_text(encoding="utf-8")
    assert "LlmCallStarted" in journal
    assert "StepTextDelta" in journal
    assert "AgentRunFinished" in journal
