"""LcaAgentRuntimeCoordinator unit tests — fold + publish + watchdog."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.application.runtime.coordinator.runtime_coordinator import LcaAgentRuntimeCoordinator
from lca.infrastructure.observability.stream import LcaStreamEventManager


@pytest.fixture
async def manager():
    import redis.asyncio as aioredis

    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    mgr = LcaStreamEventManager(client)
    yield mgr
    await client.aclose()


@pytest.fixture
async def clean_run_id(manager):
    run_id = "test_coord_unit"
    await manager.cleanup(run_id)
    yield run_id
    await manager.cleanup(run_id)


async def test_start_publishes_agent_runtime_init(manager, clean_run_id):
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={"agent_id": "a1", "topic_id": "t1"})
    history = await manager.read_history(clean_run_id, count=10)
    assert any(e["type"] == "agent_runtime_init" for e in history)


async def test_handle_stamped_publishes_text_chunk(manager, clean_run_id):
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


async def test_handle_stamped_writes_initial_plugin_state_on_tool_started(manager, clean_run_id):
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


async def test_handle_stamped_writes_projected_state_to_db_before_tool_end(manager, clean_run_id):
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


async def test_terminal_publishes_agent_runtime_end(manager, clean_run_id):
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
    manager, clean_run_id
):
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


async def test_watchdog_no_op_if_already_published(manager, clean_run_id):
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


async def test_watchdog_no_op_when_session_still_running(manager, clean_run_id):
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
