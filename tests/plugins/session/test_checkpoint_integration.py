"""ADR-0191 I-CHK-1: checkpoint fail-closed before LLM dispatch."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from lca.cognition.brain.llm_turn import execute_llm_turn
from lca.contracts.models.core.conversation.llm import LLMResponse, LLMStreamEvent
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.session.persistence.service import CheckpointFailure
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


class _AlwaysFailListener:
    async def flush(self, session: Any) -> None:
        raise OSError("disk full")


class _RecordingLLM:
    def __init__(self) -> None:
        self.stream_calls = 0
        self.complete_calls = 0

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self.complete_calls += 1
        return LLMResponse(text="should not run")

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        self.stream_calls += 1
        yield LLMStreamEvent(type="completed", response=LLMResponse(text="should not run"))  # type: ignore[arg-type]


async def test_flush_failure_blocks_llm_dispatch() -> None:
    session = Session("chk-int-1")
    session.register_flush_listener(_AlwaysFailListener())
    token = set_publish_session(session)
    state = AgentState(trace_id="t", task="hi", budget=Budget(), step=0)
    llm = _RecordingLLM()
    try:
        with pytest.raises(CheckpointFailure, match="disk full"):
            await execute_llm_turn(llm, [], "prompt", step=0, state=state, task="hi")
    finally:
        reset_publish_session(token)
    assert llm.stream_calls == 0
    assert llm.complete_calls == 0


async def test_healthy_flush_allows_llm_dispatch() -> None:
    session = Session("chk-int-2")
    token = set_publish_session(session)
    state = AgentState(trace_id="t", task="hi", budget=Budget(), step=0)

    class _OkLLM:
        async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
            return LLMResponse(text="")

        async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
            from lca.contracts.atoms.enums.enums import LLMStreamEventType

            yield LLMStreamEvent(
                type=LLMStreamEventType.COMPLETED,
                response=LLMResponse(text="ok"),
            )

    llm = _OkLLM()
    try:
        result = await execute_llm_turn(llm, [], "prompt", step=0, state=state, task="hi")
    finally:
        reset_publish_session(token)
    assert result.text == "ok"
