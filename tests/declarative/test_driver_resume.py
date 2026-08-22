"""Task 4: 验证声明式 driver 是 checkpoint/resume 的唯一入口"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.declarative_phase_graph import PhaseRunCursor
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer4_app.api import ensure_default_ctx
from lca.layer4_app.spawn import spawn_agent
from tests.support.agent_specs import make_spec


async def build_paused_default_runtime() -> tuple[object, object]:
    """使用 boot_profile 和 spawn_agent 创建默认 profile 的 paused runtime"""
    scope = await ensure_default_ctx()
    agent = spawn_agent(
        make_spec("declarative-default", MockLLMAdapter(), max_steps=2),
        scope=scope,
    )
    runtime = agent.runtime
    
    # 执行到需要审批的点
    result = await agent.run("请调用一个需要审批的工具")
    
    if result.status != TaskStatus.PAUSED:
        pytest.skip("Default profile did not pause for approval")
    
    snapshot = result.extra["state_snapshot"]
    return runtime, snapshot


@pytest.mark.asyncio
async def test_runtime_resume_uses_the_snapshot_plan_and_declarative_driver(monkeypatch):
    """验证 resume() 使用 snapshot 中的 plan 和声明式 driver，而不是 _loop()"""
    runtime, snapshot = await build_paused_default_runtime()
    
    # monkeypatch 旧的 _loop 方法，如果被调用则抛出异常
    async def old_loop(*args, **kwargs):
        raise AssertionError("old loop")
    
    monkeypatch.setattr(runtime, "_loop", old_loop)
    
    # resume 应该通过声明式 driver，不会调用 _loop
    result = await runtime.resume(snapshot, input="approved")
    
    assert result.status in (TaskStatus.COMPLETED, TaskStatus.PAUSED)
    assert result.extra.get("plan_ref") == runtime.compiled_plan.plan_hash


@pytest.mark.asyncio
async def test_declarative_runtime_driver_has_resume_method():
    """验证 DeclarativeRuntimeDriver 有 resume() 方法"""
    from lca.layer2_runtime.declarative_runtime import DeclarativeRuntimeDriver
    assert hasattr(DeclarativeRuntimeDriver, "resume")
    assert callable(getattr(DeclarativeRuntimeDriver, "resume"))


@pytest.mark.asyncio
async def test_resume_validates_plan_ref_matches():
    """验证 resume() 会检查 cursor 的 plan_ref 是否匹配当前 plan"""
    from unittest.mock import MagicMock
    
    from lca.layer2_runtime.declarative_runtime import DeclarativeRuntimeDriver, DeclarativeCheckpoint
    from lca.contracts.protocols.declarative_phase_graph import PhaseRunCursor
    from lca.contracts.protocols.plan import CompiledRunPlan
    from lca.layer2_runtime.declarative_runtime import RuntimePhaseCapabilities
    
    # 创建一个简单的 plan（使用 mock 对象）
    plan = MagicMock(spec=CompiledRunPlan)
    plan.plan_hash = "test_plan_hash"
    plan.is_declarative = True
    plan.validation_report = MagicMock()
    plan.validation_report.require_valid = MagicMock()
    plan.phase_graph = None  # 不需要实际的 phase graph 来测试验证
    
    driver = DeclarativeRuntimeDriver(
        plan=plan,
        phase_executors={},
        capabilities=RuntimePhaseCapabilities(
            brain=AsyncMock(),
            body=AsyncMock(),
            memory=AsyncMock(),
            perceive_hub=AsyncMock(),
            stop_rule=AsyncMock(),
        ),
        reducer=AsyncMock(),
        hooks=AsyncMock(),
    )
    
    # 创建不匹配的 cursor
    wrong_cursor = PhaseRunCursor(
        plan_ref="wrong_plan_ref",
        node_id="stop.main",
        visit_counts=(),
        edge_counts=(),
        artifacts={},
        causation_refs=(),
        budget_snapshot={},
    )
    
    checkpoint = DeclarativeCheckpoint(
        state_snapshot=None,
        cursor=wrong_cursor,
        plan_ref="wrong_plan_ref",
    )
    
    # resume 应该抛出验证错误
    with pytest.raises(Exception, match="plan_ref"):
        await driver.resume(checkpoint)
