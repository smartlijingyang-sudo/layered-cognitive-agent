"""ADR-0249 双轨修正：governor 追加 episode 快记（旁路副作用），语义蒸馏主流程照常运行。

原测试断言 "governor 成功路径永不触达 adapter" 是错误的 —— 它把白天快记旁路
写成了短路主流程的 early return，导致 web-assistant profile 下语义记忆永不落盘。
修正后：governor 只做 EpisodeBuffer.append 副作用，pre-filter 门控成本，
LLM 蒸馏照常产生 memory_candidates 供 remember 相 admit/write。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.models.core.execution.decision import Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.memory.episode import EpisodeFact
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.reflect.memory_extract.memory_extract import ReflectMemoryExtractExecutor


def _state(task: str) -> AgentState:
    return AgentState(trace_id="trace_t", task=task, budget=Budget())


def _reflection() -> Reflection:
    return Reflection(
        reflection_id="refl_1",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={},
    )


class _JsonLLMAdapter:
    """Stub adapter：返回固定 JSON 蒸馏文本，记录调用次数。"""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self._text, model="stub")


def _context(home: Path | None, task: str, adapter: object | None) -> NodeContext:
    runtime: dict[str, object] = {"agent_state": _state(task)}
    if home is not None:
        runtime["assistant_home_path"] = str(home)
    if adapter is not None:
        runtime["adapter"] = adapter
    return NodeContext(runtime=runtime, metadata={}, budget=None)


@pytest.mark.asyncio
async def test_governor_appends_episode_and_semantic_runs(tmp_path: Path) -> None:
    """governor 旁路写 episode，主流程 LLM 蒸馏照常产出 memory_candidates。"""
    home = tmp_path / "asst"
    adapter = _JsonLLMAdapter(
        '[{"category": "identity", "content": "用户身份：架构师", '
        '"confidence": 1.0, "dedupe_key": "identity:architect"}]'
    )
    executor = ReflectMemoryExtractExecutor(governor_enabled=True)
    reflection = _reflection()
    output = await executor.node_execute(
        _context(home, "我是架构师", adapter),
        NodeInput(port_values={"reflection": reflection}),
    )

    # 白天快记旁路：episode 文件照写
    episodes = list((home / "memory" / "episodes").glob("*.json"))
    assert len(episodes) == 1
    fact = EpisodeFact.model_validate(json.loads(episodes[0].read_text(encoding="utf-8")))
    assert fact.content == "用户身份：架构师"
    # 语义蒸馏主流程：adapter 被调用且产出 candidates
    assert adapter.calls == 1
    assert output.port_values["reflection"] is reflection
    candidates = reflection.extra.get("memory_candidates")
    assert candidates and candidates[0]["content"] == "用户身份：架构师"


@pytest.mark.asyncio
async def test_low_residual_writes_no_episode_no_distill(tmp_path: Path) -> None:
    """低残差：不写 episode；pre-filter 未命中时也不做 LLM 蒸馏。"""
    home = tmp_path / "asst"
    adapter = _JsonLLMAdapter("[]")
    executor = ReflectMemoryExtractExecutor(governor_enabled=True)
    reflection = _reflection()
    await executor.node_execute(
        _context(home, "查询北京天气", adapter),
        NodeInput(port_values={"reflection": reflection}),
    )

    assert not (home / "memory" / "episodes").exists()
    assert adapter.calls == 0
    assert reflection.extra == {}


@pytest.mark.asyncio
async def test_governor_disabled_is_fail_soft_without_episode_dir(tmp_path: Path) -> None:
    executor = ReflectMemoryExtractExecutor(governor_enabled=False)
    reflection = _reflection()
    episodes = Path.cwd() / "memory" / "episodes"
    existed = episodes.exists()
    output = await executor.node_execute(
        _context(None, "我是架构师", None),
        NodeInput(port_values={"reflection": reflection}),
    )

    assert output.port_values["reflection"] is reflection
    assert reflection.extra == {}
    assert "fast_path" not in reflection.extra
    if not existed:
        assert not episodes.exists()
    assert not (tmp_path / "memory" / "episodes").exists()
