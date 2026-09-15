"""Fail matrix for PromptReasoner SRP + no silent empty-tools fallback.

eng/retire-v1-reasoner-sandbox / ADR-0220 §6:
- complete_turn requires per-turn tools (ForkedTools or Sequence)
- no boot empty-tools fallback
- no role_profile / _tools owned assembly state
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.cognition.brain.reasoner.reasoner import PromptReasoner
from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnRender
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols import LLMAdapter


@dataclass
class _StubLLM(LLMAdapter):
    async def invoke(self, **_: object) -> object:
        raise NotImplementedError

    async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
        return LLMResponse(text="ok")


@dataclass(frozen=True)
class _Tool:
    name: str
    description: str = ""

    async def invoke(self, **_: object) -> object:
        return None


def _state() -> AgentState:
    return AgentState(trace_id="fail-matrix", task="t", budget=Budget())


def _render() -> ReasonerTurnRender:
    return ReasonerTurnRender(
        prompt="hi",
        trace=None,
        section_count=0,
        manifest=None,
        activated_skill_ids=(),
        section_outputs=None,
        total_chars=None,
        variant=None,
    )


def test_prompt_reasoner_has_no_tools_or_role_assembly_state() -> None:
    reasoner = PromptReasoner(llm=_StubLLM())
    assert not hasattr(reasoner, "role_profile")
    assert not hasattr(reasoner, "_tools")
    assert not hasattr(reasoner, "bind_boot_capabilities")


@pytest.mark.asyncio
async def test_complete_turn_rejects_missing_tools() -> None:
    reasoner = PromptReasoner(llm=_StubLLM())
    with pytest.raises(TypeError):
        await reasoner.complete_turn(_state(), _render())  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_complete_turn_accepts_forked_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    reasoner = PromptReasoner(llm=_StubLLM())
    captured: dict[str, object] = {}

    async def _fake_execute(llm, tools, prompt, **kwargs):
        captured["tools"] = list(tools)
        return LLMResponse(text="ok")

    monkeypatch.setattr(
        "lca.cognition.brain.reasoner.reasoner.execute_llm_turn",
        _fake_execute,
    )
    tools = (_Tool(name="runCommand"), _Tool(name="executeCode"))
    result = await reasoner.complete_turn(_state(), _render(), tools=tools)  # type: ignore[arg-type]
    assert result.text == "ok"
    names = [t.name for t in captured["tools"]]  # type: ignore[index]
    assert names == ["runCommand", "executeCode"]
