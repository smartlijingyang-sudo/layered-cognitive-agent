"""resolve_skill_for_exec 从 reducer state 兜底读取激活状态。

run_b9cf3095caed 中 ``activate_skill`` 成功后 ``run_skill_script`` 仍报
"未激活 skill"：``_activated_skills`` ContextVar 在工具执行间丢失。激活状态
已由 bridge 写入 reducer state（apply_activation 事件成功），因此
``resolve_skill_for_exec`` 应在 ContextVar 为空时兜底读 state.activated_skills。
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.policy.budget import Budget
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.memory.operational_skills import SkillNotFoundError
from lca.infrastructure.skills.activation.bridge import bridge as global_bridge
from lca.infrastructure.skills.activation.scope import (
    activated_skills_scope,
    register_activated,
    resolve_skill_for_exec,
)
from lca.plugins.loop.reducer.plugin import DefaultReducer


def _fresh_state() -> AgentState:
    return AgentState(trace_id="t_rfb", task="x", budget=Budget())


def test_resolve_skill_for_exec_falls_back_to_reducer_state() -> None:
    """ContextVar 为空时从 reducer state 读到已激活的 skill。"""
    state = _fresh_state()
    reducer = DefaultReducer()
    global_bridge.dispose()
    global_bridge.install(reducer=reducer, state_getter=lambda: state)
    try:
        # 模拟 activate_skill 的 bridge 路径（ContextVar 被写入后又被清空）
        register_activated("create-assistant", "create-assistant")
        assert len(state.activated_skills) == 1
        with activated_skills_scope(()):
            result = resolve_skill_for_exec("create-assistant")
            assert result.skill_id == "create-assistant"
    finally:
        global_bridge.dispose()


def test_resolve_skill_for_exec_raises_when_state_empty() -> None:
    """reducer state 也没有时仍按原行为抛 SkillNotFoundError。"""
    state = _fresh_state()
    reducer = DefaultReducer()
    global_bridge.dispose()
    global_bridge.install(reducer=reducer, state_getter=lambda: state)
    try:
        with activated_skills_scope(()), pytest.raises(
            SkillNotFoundError, match="未激活 skill"
        ):
            resolve_skill_for_exec("create-assistant")
    finally:
        global_bridge.dispose()
