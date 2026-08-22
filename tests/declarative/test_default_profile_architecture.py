from __future__ import annotations

import pytest

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer4_app.api import ensure_default_ctx
from lca.layer4_app.spawn import spawn_agent
from tests.support.agent_specs import make_spec


@pytest.mark.asyncio
async def test_default_profile_agent_runs_compiled_phase_graph_not_legacy_loop() -> None:
    """真实 boot/assemble/run 必须进入 GenericPlanInterpreter，而非 ``_loop``。"""

    scope = await ensure_default_ctx()
    agent = spawn_agent(
        make_spec("declarative-default", MockLLMAdapter(), max_steps=1),
        scope=scope,
    )
    runtime = agent.runtime
    assert runtime.compiled_plan is not None
    assert runtime.compiled_plan.is_declarative
    assert len(runtime.phase_executors) == 6

    async def legacy_loop_must_not_run(*_args, **_kwargs):
        raise AssertionError("default Profile fell back to CognitiveRuntime._loop")

    runtime._loop = legacy_loop_must_not_run
    result = await agent.run("请简洁地说明声明式图的作用")

    assert result.status is TaskStatus.COMPLETED
    assert result.output
