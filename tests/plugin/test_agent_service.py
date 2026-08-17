"""Tests for the agent_service plugin."""

from __future__ import annotations

import pytest

from lca.contracts.harness.events import (
    AssistantResponded,
    StepEnded,
    StepStarted,
    ToolCalled,
    ToolCompleted,
    TurnEnded,
    TurnStarted,
)
from lca.plugins.agent_service import AgentService, apply


class FakeStore:
    """Captures all events appended to it for assertion."""

    def __init__(self) -> None:
        self.events: list[tuple[object, str | None]] = []

    async def append(self, event_data: object, *, actor: str | None = None) -> None:
        self.events.append((event_data, actor))


@pytest.fixture
def service() -> AgentService:
    return AgentService()


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.mark.asyncio
async def test_record_assistant_response(service: AgentService, store: FakeStore) -> None:
    await service.record_assistant_response(store, turn=1, step=2, content="hello")
    assert len(store.events) == 1
    event, actor = store.events[0]
    assert isinstance(event, AssistantResponded)
    assert event.turn == 1
    assert event.step == 2
    assert event.content == "hello"
    assert event.tool_calls is None
    assert actor == "agent_service"


@pytest.mark.asyncio
async def test_record_assistant_response_with_tool_calls(
    service: AgentService,
    store: FakeStore,
) -> None:
    await service.record_assistant_response(
        store,
        turn=1,
        step=1,
        content="using tools",
        tool_calls=[{"id": "call_1"}, {"id": "call_2"}],
    )
    event, _ = store.events[0]
    assert isinstance(event, AssistantResponded)
    assert event.tool_calls == [{"id": "call_1"}, {"id": "call_2"}]


@pytest.mark.asyncio
async def test_record_tool_call(service: AgentService, store: FakeStore) -> None:
    await service.record_tool_call(
        store,
        turn=1,
        step=1,
        call_id="c1",
        tool_name="search",
        arguments_ref="ref://args",
    )
    assert len(store.events) == 1
    event, actor = store.events[0]
    assert isinstance(event, ToolCalled)
    assert event.call_id == "c1"
    assert event.tool_name == "search"
    assert event.arguments_ref == "ref://args"
    assert actor == "agent_service"


@pytest.mark.asyncio
async def test_record_tool_result(service: AgentService, store: FakeStore) -> None:
    await service.record_tool_result(
        store,
        turn=1,
        step=1,
        call_id="c1",
        success=True,
        result_ref="ref://result",
    )
    event, actor = store.events[0]
    assert isinstance(event, ToolCompleted)
    assert event.call_id == "c1"
    assert event.success is True
    assert event.result_ref == "ref://result"
    assert event.error is None
    assert actor == "agent_service"


@pytest.mark.asyncio
async def test_record_tool_result_with_error(
    service: AgentService,
    store: FakeStore,
) -> None:
    await service.record_tool_result(
        store,
        turn=1,
        step=1,
        call_id="c1",
        success=False,
        result_ref="",
        error="boom",
    )
    event, _ = store.events[0]
    assert isinstance(event, ToolCompleted)
    assert event.success is False
    assert event.error == "boom"


@pytest.mark.asyncio
async def test_record_turn_boundary_start(
    service: AgentService,
    store: FakeStore,
) -> None:
    await service.record_turn_boundary(store, turn=3, event_type="start")
    event, actor = store.events[0]
    assert isinstance(event, TurnStarted)
    assert event.turn == 3
    assert actor == "agent_service"


@pytest.mark.asyncio
async def test_record_turn_boundary_end(
    service: AgentService,
    store: FakeStore,
) -> None:
    await service.record_turn_boundary(store, turn=3, event_type="end")
    event, _ = store.events[0]
    assert isinstance(event, TurnEnded)
    assert event.turn == 3
    assert event.reason == "completed"


@pytest.mark.asyncio
async def test_record_turn_boundary_invalid(
    service: AgentService,
    store: FakeStore,
) -> None:
    with pytest.raises(ValueError, match="Unknown turn event_type"):
        await service.record_turn_boundary(store, turn=1, event_type="middle")


@pytest.mark.asyncio
async def test_record_step_boundary_start(
    service: AgentService,
    store: FakeStore,
) -> None:
    await service.record_step_boundary(store, turn=1, step=2, event_type="start")
    event, actor = store.events[0]
    assert isinstance(event, StepStarted)
    assert event.turn == 1
    assert event.step == 2
    assert actor == "agent_service"


@pytest.mark.asyncio
async def test_record_step_boundary_end(
    service: AgentService,
    store: FakeStore,
) -> None:
    await service.record_step_boundary(store, turn=1, step=2, event_type="end")
    event, _ = store.events[0]
    assert isinstance(event, StepEnded)
    assert event.turn == 1
    assert event.step == 2


@pytest.mark.asyncio
async def test_record_step_boundary_invalid(
    service: AgentService,
    store: FakeStore,
) -> None:
    with pytest.raises(ValueError, match="Unknown step event_type"):
        await service.record_step_boundary(store, turn=1, step=1, event_type="mid")


def test_apply_mounts_service() -> None:
    """apply() should mount AgentService at the agent_service seam."""
    mounted: dict[str, object] = {}

    class FakeCtx:
        def mount(self, key: str, svc: object) -> None:
            mounted[key] = svc

    apply(FakeCtx(), config=None)
    assert "agent_service" in mounted
    assert isinstance(mounted["agent_service"], AgentService)
