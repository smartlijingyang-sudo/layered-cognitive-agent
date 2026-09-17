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


async def test_tool_end_with_content_publishes_followup_text_chunk(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """spine body.tool.execute.end with textual result must surface the answer
    to the LobeHub client as an assistant bubble.

    Replicates the live run ``run_634aefcbb06f`` failure: after a tool returns
    ``result.content = "Example Domain"``, the LLM driver stops without
    re-emitting text, so the assistant bubble stays empty. The coordinator
    follows up ``tool_end`` with a single ``stream_chunk chunkType=text``
    carrying the tool result, so the front-end ``accumulatedContent``
    accumulator has the answer when ``agent_runtime_end`` lands.
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
                "execution_point": "body.tool.execute.end",
                "payload": {
                    "tool_name": "runCommand",
                    "invocation_id": "tc1",
                    "ok": True,
                    "latency_ms": 120,
                    "message": {
                        "role": "tool",
                        "tool_call_id": "tc1",
                        "content": "Example Domain\n",
                    },
                },
            }
        },
    )
    history = await manager.read_history(clean_run_id, count=20)
    tool_ends = [e for e in history if e["type"] == "tool_end"]
    assert len(tool_ends) == 1
    assert tool_ends[0]["data"]["result"]["content"] == "Example Domain\n"

    text_chunks_after_tool_end = [
        e
        for e in history
        if e["type"] == "stream_chunk"
        and e["data"]["chunkType"] == "text"
        and e["data"]["content"] == "Example Domain\n"
    ]
    assert len(text_chunks_after_tool_end) == 1, (
        "tool_end with textual result must emit a follow-up stream_chunk text "
        "so the assistant bubble renders the answer when the LLM driver stops"
    )
    # read_history returns newest-first; the follow-up text chunk must be
    # NEWER than tool_end (i.e. appear earlier in the list), since the
    # coordinator publishes tool_end first and the follow-up immediately after.
    text_index = history.index(text_chunks_after_tool_end[0])
    tool_end_index = history.index(tool_ends[0])
    assert text_index < tool_end_index, (
        "the follow-up text chunk must publish AFTER tool_end so the front-end "
        "sees the answer after the tool card"
    )


async def test_tool_end_with_projected_state_does_not_dump_content_into_assistant(
    manager: LcaStreamEventLog, clean_run_id: str
) -> None:
    """activate_skill (and other card-owned tools) put SKILL.md / stdout in
    ``result.content`` AND ``result.state``. Mirroring that onto a
    ``stream_chunk text`` dumps the card body into the assistant reply.
    """
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    skill_md = "# Office CLI\n\nUse officecli --json."
    await coord.handle_stamped(
        clean_run_id,
        {
            "event": {
                "type": "ToolInvoked",
                "isSuccess": True,
                "output_text": skill_md,
                "projected_state": {
                    "name": "officecli",
                    "title": "officecli",
                    "content": skill_md,
                },
                "payload": {
                    "toolCalling": {
                        "id": "tc_skill",
                        "identifier": "lobe-skills",
                        "apiName": "activateSkill",
                    }
                },
            }
        },
    )
    history = await manager.read_history(clean_run_id, count=20)
    tool_ends = [e for e in history if e["type"] == "tool_end"]
    assert len(tool_ends) == 1
    assert tool_ends[0]["data"]["result"]["content"] == skill_md
    assert tool_ends[0]["data"]["result"]["state"]["name"] == "officecli"
    assert not any(
        e["type"] == "stream_chunk"
        and e["data"].get("chunkType") == "text"
        and e["data"].get("content") == skill_md
        for e in history
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
