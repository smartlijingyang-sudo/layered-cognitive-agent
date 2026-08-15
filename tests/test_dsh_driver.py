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
    # Caller explicitly finishes the projector with actual output (new contract)
    projector.finish(status="completed", output="hi")

    kinds = [type(event).__name__ for event in sink.events]
    assert kinds[0] == "AgentRunStarted"
    assert kinds[1] == "LlmCallStarted"
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
    from lca.contracts.models.core.plane import PlaneBindings, PlaneKind, PlaneRef

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

    machine = PlaneRef(
        id="dev1",
        label="sandbox-user",
        kind=PlaneKind.MACHINE,
        root=str(tmp_path),
        outputs_dir=str(tmp_path / "outputs"),
    )
    bindings = PlaneBindings(primary=machine)

    class _Transport:
        async def computer_op(self, op: str, args: dict, *, timeout_s: int = 60) -> dict:
            del op, args, timeout_s
            return {"success": True, "files": []}

        async def write_files(
            self, files: dict, *, base_dir: str = "", session_id: str = "", timeout_s: int = 60
        ):
            del files, base_dir, session_id, timeout_s
            return {"success": True}

    async def _noop_stage(session: object) -> None:
        del session

    async def _fake_machine_turn(**kwargs: object) -> DshTurnResult:
        from lca.layer0_infra.dsh.archive import JsonlEventArchive
        from lca.layer0_infra.dsh.projector import DshJournalProjector
        from lca.layer0_infra.dsh.sink import FacadeJournalSink

        runtime = kwargs["runtime"]
        run_id = str(kwargs["run_id"])
        question = str(kwargs["question"])
        runs_dir = kwargs["runs_dir"]
        driver = DshTurnDriver(
            runtime=runtime,  # type: ignore[arg-type]
            projector=DshJournalProjector(FacadeJournalSink()),
            archive=JsonlEventArchive(runs_dir / f"{run_id}.dsh.jsonl"),
        )
        return driver.run(
            DshTurnSpec(
                prompt=question,
                session_id=run_id,
                cwd=str(tmp_path),
                session_root=str(runs_dir),
            )
        )

    monkeypatch.setattr("gateway.runs.execute._freeze_bindings", lambda session: bindings)
    monkeypatch.setattr("gateway.runs.execute._stage_machine_attachments", _noop_stage)
    monkeypatch.setattr(
        "gateway.runs.dsh_execute.resolve_machine_transport", lambda _id: _Transport()
    )
    monkeypatch.setattr(
        "gateway.runs.dsh_execute.default_runtime",
        lambda _s, *, transport=None, machine=None: fake,
    )
    monkeypatch.setattr("gateway.runs.dsh_execute.run_dsh_machine_turn", _fake_machine_turn)

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
    archive = tmp_path / f"{session.run_id}.dsh.jsonl"
    assert archive.is_file()
    journal = session.jsonl_path.read_text(encoding="utf-8")
    assert "LlmCallStarted" in journal
    assert "StepTextDelta" in journal
    assert "AgentRunFinished" in journal


def test_compose_dsh_prompt_includes_prior_turns_only() -> None:
    from lca.contracts.models.core.conversation import ConversationTurn
    from lca.layer0_infra.dsh.prompt import compose_dsh_prompt

    prompt = compose_dsh_prompt(
        "analyze file",
        (ConversationTurn(role="user", content="hi"),),
    )
    assert "Prior conversation" in prompt
    assert "user: hi" in prompt
    assert "analyze file" in prompt
    assert "Working root" not in prompt
    assert "staged copies" not in prompt


def test_build_harness_env_sets_paths_not_prompts(tmp_path: Path) -> None:
    from lca.contracts.models.core.plane import PlaneKind, PlaneRef
    from lca.layer0_infra.dsh.launch import build_harness_env

    machine = PlaneRef(
        id="dev1",
        label="sandbox-user",
        kind=PlaneKind.MACHINE,
        root="/home/sandbox-user",
        outputs_dir="/home/sandbox-user/outputs",
    )
    runs = tmp_path / "runs"
    env = build_harness_env(machine, run_id="run_abc", session_root=runs)
    assert env["LCA_MACHINE_ROOT"] == "/home/sandbox-user"
    assert env["LCA_OUTPUTS_DIR"] == "/home/sandbox-user/outputs"
    assert env["LCA_INBOX_DIR"] == "/home/sandbox-user/.lca/inbox/run_abc"
    assert env["LCA_RUN_ID"] == "run_abc"
    assert env["DSH_SESSION_ROOT"] == str(runs)


def test_build_harness_env_injects_uploaded_files_context(tmp_path: Path) -> None:
    from lca.contracts.models.core.plane import PlaneKind, PlaneRef
    from lca.layer0_infra.dsh.launch import build_harness_env
    from lca.layer0_infra.file_store import LocalFileStore

    store = LocalFileStore(root=tmp_path / "files")
    meta = store.put(data=b"deck", name="deck.pptx", mime_type="application/vnd.ms-powerpoint")
    machine = PlaneRef(
        id="dev1",
        label="sandbox-user",
        kind=PlaneKind.MACHINE,
        root="/home/sandbox-user",
        outputs_dir="/home/sandbox-user/outputs",
    )
    env = build_harness_env(
        machine,
        run_id="run_abc",
        session_root=tmp_path / "runs",
        attachment_ids=(meta.attachment_id,),
        store=store,
    )
    prompt = env.get("DSH_SYSTEM_PROMPT", "")
    assert "<uploaded_files>" in prompt
    assert "/home/sandbox-user/.lca/inbox/run_abc/deck.pptx" in prompt


class _FakeTransport:
    """In-memory MachineTransport for MachineDshRuntime tests."""

    def __init__(
        self,
        *,
        runner_output: str = '{"session_id":"s1","final_response":"ok","finish_reason":"completed"}',
        events_content: str = "",
        op_success: bool = True,
    ) -> None:
        self.written: dict[str, str] = {}
        self.commands: list[dict] = []
        self._runner_output = runner_output
        self._events_content = events_content
        self._op_success = op_success

    async def computer_op(self, op: str, args: dict, *, timeout_s: int = 60) -> dict:
        self.commands.append({"op": op, "args": args})
        if op == "runCommand":
            return {"success": self._op_success, "content": self._runner_output}
        if op == "readFile":
            return {"success": True, "content": self._events_content}
        return {"success": True}

    async def write_files(
        self, files: dict, *, base_dir: str = "", session_id: str = "", timeout_s: int = 60
    ):
        self.written.update(files)
        return {"success": True}


def test_machine_runtime_writes_runner_and_config(tmp_path: Path) -> None:
    import json

    from lca.contracts.models.core.plane import PlaneKind, PlaneRef
    from lca.layer0_infra.dsh.driver import DshTurnSpec
    from lca.layer0_infra.dsh.machine_runtime import MachineDshRuntime
    from lca.layer0_infra.dsh.settings import DshSettings

    transport = _FakeTransport(
        events_content='{"method":"session.event","payload":{"event":{"type":"turn/start"}}}\n'
    )
    machine = PlaneRef(
        id="dev1",
        label="sandbox-user",
        kind=PlaneKind.MACHINE,
        root=str(tmp_path),
        outputs_dir=str(tmp_path / "outputs"),
    )
    runtime = MachineDshRuntime(transport, machine, DshSettings())
    events: list = []
    spec = DshTurnSpec(
        prompt="hello",
        session_id="run_1",
        cwd=str(tmp_path),
        session_root=str(tmp_path),
    )
    result = runtime.run_turn(spec, events.append)

    assert result.session_id == "s1"
    assert result.final_response == "ok"
    assert result.finish_reason == "completed"

    assert any("runner.py" in k for k in transport.written)
    assert any("config.json" in k for k in transport.written)

    config = json.loads(transport.written[".lca/dsh/config.json"])
    assert config["prompt"] == "hello"
    assert config["session_id"] == "run_1"
    assert config["cwd"] == str(tmp_path)
    assert "events_path" in config

    assert len(events) == 1
    assert events[0].method == "session.event"


def test_machine_runtime_handles_runner_failure(tmp_path: Path) -> None:
    from lca.contracts.models.core.plane import PlaneKind, PlaneRef
    from lca.layer0_infra.dsh.driver import DshTurnSpec
    from lca.layer0_infra.dsh.machine_runtime import MachineDshRuntime
    from lca.layer0_infra.dsh.settings import DshSettings

    transport = _FakeTransport(op_success=False, runner_output="error")
    machine = PlaneRef(
        id="dev1",
        label="sandbox-user",
        kind=PlaneKind.MACHINE,
        root=str(tmp_path),
        outputs_dir=str(tmp_path / "outputs"),
    )
    runtime = MachineDshRuntime(transport, machine, DshSettings())
    events: list = []
    spec = DshTurnSpec(
        prompt="hello",
        session_id="run_1",
        cwd=str(tmp_path),
        session_root=str(tmp_path),
    )
    result = runtime.run_turn(spec, events.append)
    assert result.finish_reason == "failed"
    assert any(e.method == "session.error" for e in events)
