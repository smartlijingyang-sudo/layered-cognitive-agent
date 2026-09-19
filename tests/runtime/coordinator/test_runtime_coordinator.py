"""LcaAgentRuntimeCoordinator unit tests — fold + publish + watchdog."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.application.runtime.coordinator.runtime_coordinator import LcaAgentRuntimeCoordinator
from lca.infrastructure.observability.stream import LcaStreamEventLog


@pytest.fixture
async def manager() -> AsyncIterator[LcaStreamEventLog]:
    import redis.asyncio as aioredis

    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    mgr = LcaStreamEventLog(client)
    yield mgr
    await client.aclose()


@pytest.fixture
async def clean_run_id(manager: LcaStreamEventLog) -> AsyncIterator[str]:
    run_id = "test_coord_unit"
    await manager.cleanup(run_id)
    yield run_id
    await manager.cleanup(run_id)


async def test_start_publishes_agent_runtime_init(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={"agent_id": "a1", "topic_id": "t1"})
    history = await manager.read_history(clean_run_id, count=10)
    assert any(e["type"] == "agent_runtime_init" for e in history)


async def test_handle_stamped_publishes_text_chunk(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    await coord.handle_stamped(
        clean_run_id, {"event": {"type": "LlmCallTextDelta", "delta": "hello"}}
    )
    history = await manager.read_history(clean_run_id, count=10)
    text_chunks = [
        e for e in history if e["type"] == "stream_chunk" and e["data"]["chunkType"] == "text"
    ]
    assert any(c["data"]["content"] == "hello" for c in text_chunks)


async def test_handle_stamped_writes_initial_plugin_state_on_tool_started(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """tool_start: persist identifier/apiName/args before the WS event."""
    tool_state_writer = AsyncMock()
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=tool_state_writer,
    )
    await coord.start(clean_run_id, ctx={})
    await coord.handle_stamped(
        clean_run_id,
        {
            "event": {
                "type": "ToolStarted",
                "payload": {
                    "id": "tc1",
                    "identifier": "lobe-cloud-sandbox",
                    "apiName": "executeCode",
                    "arguments": {"code": "print(1)", "language": "python"},
                    "type": "builtin",
                },
            }
        },
    )
    assert tool_state_writer.call_count == 1
    state = tool_state_writer.call_args.kwargs.get("state", {})
    assert state.get("code") == "print(1)"
    assert state.get("apiName") == "executeCode"


async def test_handle_stamped_writes_projected_state_to_db_before_tool_end(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """spec §5.3.1: server must write projected_state to message row BEFORE tool_end."""
    tool_state_writer = AsyncMock()
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=tool_state_writer,
    )
    await coord.start(clean_run_id, ctx={})
    await coord.handle_stamped(
        clean_run_id,
        {
            "event": {
                "type": "ToolInvoked",
                "payload": {
                    "toolCalling": {
                        "id": "tc1",
                        "identifier": "lobe-local-system",
                        "apiName": "runCommand",
                        "arguments": {"command": "ls"},
                        "type": "builtin",
                    }
                },
                "result": {"content": "ok"},
                "isSuccess": True,
                "executionTime": 120,
                "projected_state": {"stdout": "ok", "exitCode": 0},
            }
        },
    )
    # The DB write must have happened BEFORE the tool_end was published
    assert tool_state_writer.call_count == 1
    call_args = tool_state_writer.call_args
    assert call_args.kwargs.get("run_id") == clean_run_id
    assert call_args.kwargs.get("tool_call_id") == "tc1"
    assert "stdout" in call_args.kwargs.get("state", {})
    # The tool_end event must be in the stream
    history = await manager.read_history(clean_run_id, count=10)
    assert any(e["type"] == "tool_end" for e in history)


async def test_tool_end_never_mirrors_result_into_assistant_text(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """Every tool result belongs on the tool card. Mirroring ``result.content``
    into a ``stream_chunk text`` dumps stdout / SKILL.md into the assistant
    bubble. Native LobeHub never does this.
    """
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    stdout = "Example Domain\n"
    await coord.handle_stamped(
        clean_run_id,
        {
            "event": {
                "execution_point": "body.tool.execute.end",
                "payload": {
                    "tool_name": "runCommand",
                    "invocation_id": "tc1",
                    "ok": True,
                    "latency_ms": 120,
                    "message": {
                        "role": "tool",
                        "tool_call_id": "tc1",
                        "content": stdout,
                    },
                },
            }
        },
    )
    history = await manager.read_history(clean_run_id, count=20)
    tool_ends = [e for e in history if e["type"] == "tool_end"]
    assert len(tool_ends) == 1
    assert tool_ends[0]["data"]["result"]["content"] == stdout
    assert not any(
        e["type"] == "stream_chunk" and e["data"].get("chunkType") == "text" for e in history
    )


async def test_tool_end_without_content_does_not_emit_text_chunk(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """No tool text → no synthetic assistant text chunk (preserves the
    wait-for-LLM path for tool runs that legitimately need a follow-up)."""
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    await coord.handle_stamped(
        clean_run_id,
        {
            "event": {
                "execution_point": "body.tool.execute.end",
                "payload": {
                    "tool_name": "runCommand",
                    "invocation_id": "tc2",
                    "ok": True,
                    "latency_ms": 50,
                },
            }
        },
    )
    history = await manager.read_history(clean_run_id, count=20)
    assert not any(
        e["type"] == "stream_chunk" and e["data"]["chunkType"] == "text" for e in history
    )


async def test_terminal_publishes_agent_runtime_end(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    await coord.terminal(clean_run_id, status="done", final_state={"status": "done"})
    history = await manager.read_history(clean_run_id, count=10)
    end_events = [e for e in history if e["type"] == "agent_runtime_end"]
    assert len(end_events) == 1
    assert end_events[0]["data"]["reason"] == "done"
    assert end_events[0]["data"]["phase"] == "execution_complete"


async def test_watchdog_publishes_synthetic_terminal_if_session_terminal_but_no_spine_event(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """spec §1 broken #3: parent run with no live SpineClose must not hang the stream."""
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    # session is terminal but no SpineClose has been emitted
    session = MagicMock()
    session.status = "done"
    session.error = None
    session.final_state = {"status": "done"}
    await coord.synthesize_terminal_if_pending(clean_run_id, session=session)
    history = await manager.read_history(clean_run_id, count=10)
    assert any(
        e["type"] == "agent_runtime_end" and e["data"]["reason"] == "completed" for e in history
    )


async def test_watchdog_no_op_if_already_published(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """The watchdog must not double-publish if the natural SpineClose already fired."""
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    # Natural terminal fires first
    await coord.terminal(clean_run_id, status="done", final_state={"status": "done"})
    before_count = len(
        [
            e
            for e in await manager.read_history(clean_run_id, count=100)
            if e["type"] == "agent_runtime_end"
        ]
    )
    # Watchdog fires
    session = MagicMock()
    session.status = "done"
    session.error = None
    session.final_state = {"status": "done"}
    await coord.synthesize_terminal_if_pending(clean_run_id, session=session)
    after_count = len(
        [
            e
            for e in await manager.read_history(clean_run_id, count=100)
            if e["type"] == "agent_runtime_end"
        ]
    )
    assert before_count == after_count  # no duplicate


async def test_watchdog_no_op_when_session_still_running(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    session = MagicMock()
    session.status = "running"
    session.error = None
    await coord.synthesize_terminal_if_pending(clean_run_id, session=session)
    history = await manager.read_history(clean_run_id, count=10)
    assert not any(e["type"] == "agent_runtime_end" for e in history)


async def test_handle_stamped_hitl_pause_publishes_step_start_then_runtime_end(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """HITL pause (spec §5.2): ``step_start{human_approval}`` precedes ``agent_runtime_end``.

    The front-end replays the stream in order; the approval card state must
    exist before the terminal event closes the live run.
    """
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    await coord.handle_stamped(
        clean_run_id,
        {
            "event": {
                "type": "SpineClose",
                "reason": "waiting_for_human",
                "final_state": {"status": "waiting_for_human"},
            }
        },
    )
    history = await manager.read_history(clean_run_id, count=10)
    # read_history returns newest first; reverse to delivery order.
    ordered = list(reversed(history))
    types = [e["type"] for e in ordered if e["type"] in ("step_start", "agent_runtime_end")]
    assert types == ["step_start", "agent_runtime_end"]
    step_start = next(e for e in history if e["type"] == "step_start")
    assert step_start["data"]["phase"] == "human_approval"
    assert step_start["data"]["requiresApproval"] is True
    end = next(e for e in history if e["type"] == "agent_runtime_end")
    assert end["data"]["reason"] == "waiting_for_human"
    # The natural terminal is recorded so the watchdog does not double-publish.
    session = MagicMock()
    session.status = "done"
    session.error = None
    session.final_state = {"status": "done"}
    await coord.synthesize_terminal_if_pending(clean_run_id, session=session)
    after = await manager.read_history(clean_run_id, count=10)
    assert len([e for e in after if e["type"] == "agent_runtime_end"]) == 1


async def test_handle_stamped_attaches_artifact_closure_to_agent_runtime_end(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """Regression: artifact closure rides the terminal event, not per-tool wire.

    exportFile's projected state carries no ``files`` field, so a client that
    folds per-tool ``tool_end`` results misses the deliverable. The closure
    must be synthesized from the run workspace ledger and attached to
    ``agent_runtime_end`` atomically.
    """

    async def resolver(run_id: str) -> dict | None:
        assert run_id == clean_run_id
        return {
            "text": "已生成以下文件：\n- [📥 report.pdf](/files/file_abc)",
            "files": [
                {
                    "name": "report.pdf",
                    "url": "/files/file_abc",
                    "mimeType": "application/pdf",
                    "sizeBytes": 92160,
                    "attachmentId": "file_abc",
                    "previewable": True,
                }
            ],
        }

    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
        artifact_closure_resolver=resolver,
    )
    await coord.start(clean_run_id, ctx={})
    await coord.handle_stamped(
        clean_run_id,
        {
            "event": {
                "type": "SpineClose",
                "reason": "completed",
                "final_state": {"status": "done"},
            }
        },
    )
    history = await manager.read_history(clean_run_id, count=10)
    end = next(e for e in history if e["type"] == "agent_runtime_end")
    assert end["data"]["reason"] == "completed"
    assert end["data"]["artifactClosure"]["text"].startswith("已生成以下文件")
    assert end["data"]["artifactClosure"]["files"][0]["name"] == "report.pdf"


async def test_handle_stamped_omits_artifact_closure_when_resolver_returns_none(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """No workspace deliverables -> terminal event carries no closure."""

    async def resolver(run_id: str) -> dict | None:
        assert run_id == clean_run_id
        return None

    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
        artifact_closure_resolver=resolver,
    )
    await coord.start(clean_run_id, ctx={})
    await coord.handle_stamped(
        clean_run_id,
        {
            "event": {
                "type": "SpineClose",
                "reason": "completed",
                "final_state": {"status": "done"},
            }
        },
    )
    history = await manager.read_history(clean_run_id, count=10)
    end = next(e for e in history if e["type"] == "agent_runtime_end")
    assert "artifactClosure" not in end["data"]
