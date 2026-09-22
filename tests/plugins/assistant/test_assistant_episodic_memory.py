"""Tests for AssistantMemory episodic memory generation and rolling window."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import MemoryLayer, ReflectionVerdict
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.infrastructure.memory.assistant_memory import AssistantMemory


@pytest.mark.asyncio
async def test_assistant_memory_persists_episodic_on_tool_execution(tmp_path: Path):
    mem = AssistantMemory(tmp_path / "asst")
    state = AgentState(trace_id="t1", task="执行代码检查并修复漏洞", step=1, budget=Budget())
    obs = Observation(
        observation_id="o1",
        success=True,
        payload={"tool": "run_command", "output": "code check passed with 0 errors"},
    )
    refl = Reflection(reflection_id="r1", verdict=ReflectionVerdict.ON_TRACK, extra={})

    await mem.update(state, obs, refl)

    episodic = mem.query(MemoryLayer.EPISODIC)
    assert len(episodic) == 1
    assert "执行代码检查" in episodic[0].content
    assert "run_command" in episodic[0].content
    assert episodic[0].importance >= 0.7

    # 验证落盘文件正确性
    episodic_file = tmp_path / "asst" / "memory" / "episodic.json"
    assert episodic_file.is_file()
    records = json.loads(episodic_file.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert records[0]["layer"] == "episodic"


@pytest.mark.asyncio
async def test_assistant_memory_episodic_rolling_limit(tmp_path: Path):
    mem = AssistantMemory(tmp_path / "asst")
    # 模拟写入 60 条工具执行情景记忆
    for i in range(60):
        state = AgentState(trace_id=f"t_{i}", task=f"任务步骤 {i}", step=1, budget=Budget())
        obs = Observation(
            observation_id=f"obs_{i}",
            success=True,
            payload={"tool": f"tool_{i}", "output": f"ok_{i}"},
        )
        refl = Reflection(reflection_id=f"r_{i}", verdict=ReflectionVerdict.ON_TRACK, extra={})
        await mem.update(state, obs, refl)

    episodic = mem.query(MemoryLayer.EPISODIC)
    # 容量必须受限在 50 条以内
    assert len(episodic) == 50
    # FIFO: 最旧的 0~9 应当被淘汰，最新的 10~59 被保留
    assert "任务步骤 59" in episodic[-1].content
    assert "任务步骤 0" not in [r.content for r in episodic]
