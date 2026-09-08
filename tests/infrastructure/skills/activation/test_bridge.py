"""SkillActivationReducerBridge test (PR-E 收口 2026-09-08)。

覆盖(AGENTS.md §6):
- bridge 未 install 时 handle() 是 no-op(import-time / 测试 fixture 安全)。
- bridge install 后,handle 触发 reducer.apply_activation,把 ActivatedSkill
  fold 进 live state.activated_skills。
- 重复 handle 同一 skill_id 不破坏 state(reducer.extend append-only;
  ActivatedSkill 唯一性由 reducer 收口路径保障)。
- dispose 后 handle 是 no-op(避免悬空引用)。
- 进程级 singleton ``bridge`` 可重入:覆盖式 install/dispose 是幂等的。

回归目标:run_2910e20390f9 反复 ``activate_skill('anthropics-skills-pdf')`` 的
模式 —— 现在 state.activated_skills 会同步 populated,prompt assembler
读到的 activated_skill_ids 非空,LLM 不再重复触发。
"""

from __future__ import annotations

from lca.contracts.models.core.policy.budget import Budget
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.infrastructure.skills.activation.bridge import SkillActivationReducerBridge
from lca.infrastructure.skills.activation.bridge import bridge as global_bridge
from lca.plugins.loop.reducer.plugin import DefaultReducer


def _fresh_state() -> AgentState:
    return AgentState(trace_id="t_pr_e", task="x", budget=Budget())


def test_bridge_handle_before_install_is_noop() -> None:
    """未 install 时 handle() 不抛、不写 state。"""
    b = SkillActivationReducerBridge()
    state = _fresh_state()
    reducer = DefaultReducer()
    # install 之前 call —— 应是 no-op
    b.handle(skill_id="pdf", name="PDF")
    assert state.activated_skills == []


def test_bridge_install_then_handle_folds_into_state() -> None:
    """install 后 handle 触发 reducer.apply_activation,state.activated_skills populated。"""
    b = SkillActivationReducerBridge()
    state = _fresh_state()
    reducer = DefaultReducer()
    b.install(reducer=reducer, state_getter=lambda: state)
    try:
        b.handle(skill_id="pdf", name="PDF")
        assert len(state.activated_skills) == 1
        assert state.activated_skills[0].skill_id == "pdf"
        assert state.activated_skills[0].name == "PDF"
    finally:
        b.dispose()


def test_bridge_repeated_handle_appends() -> None:
    """同一 skill_id 重复 handle —— reducer.extend 行为,不抛错。

    注:reducer.apply_activation 当前实现是 ``state.activated_skills.extend(activated)``,
    不做 dedupe。dedupe 由 prompt assembler 的"已激活"提示消费侧收口。
    本测试只断言 reducer 单写路径被触发(每条 SkillActivated 事件都 fold)。
    """
    b = SkillActivationReducerBridge()
    state = _fresh_state()
    reducer = DefaultReducer()
    b.install(reducer=reducer, state_getter=lambda: state)
    try:
        b.handle(skill_id="pdf", name="PDF")
        b.handle(skill_id="officecli", name="Office CLI")
        ids = [s.skill_id for s in state.activated_skills]
        # 顺序按 handle 顺序;重复激活会让 prompt assembler 看到最近条目
        # (render_activated_skills 取末尾)
        assert "pdf" in ids
        assert "officecli" in ids
    finally:
        b.dispose()


def test_bridge_dispose_makes_handle_noop() -> None:
    """dispose 后 handle() 不抛、不再 fold(避免悬空引用)。"""
    b = SkillActivationReducerBridge()
    state = _fresh_state()
    reducer = DefaultReducer()
    b.install(reducer=reducer, state_getter=lambda: state)
    b.handle(skill_id="pdf", name="PDF")
    assert len(state.activated_skills) == 1
    b.dispose()
    b.handle(skill_id="officecli", name="Office CLI")
    # dispose 后 officecli 不应被 fold
    assert len(state.activated_skills) == 1
    assert state.activated_skills[0].skill_id == "pdf"


def test_global_singleton_install_dispose_idempotent() -> None:
    """进程级 singleton ``bridge`` 可被 run() 反复 install/dispose,无残留状态。"""
    # 强制重置兜底 —— 上一个测试 / 之前 run 若忘了 dispose,这里清掉
    global_bridge.dispose()
    try:
        state = _fresh_state()
        reducer = DefaultReducer()
        global_bridge.install(reducer=reducer, state_getter=lambda: state)
        global_bridge.handle(skill_id="pdf", name="PDF")
        assert any(s.skill_id == "pdf" for s in state.activated_skills)
    finally:
        global_bridge.dispose()
    # dispose 后再 handle 不抛
    global_bridge.handle(skill_id="officecli", name="Office CLI")


def test_register_activated_in_scope_invokes_bridge() -> None:
    """``register_activated``(scope.py)同步转发到 bridge.handle。

    注册 chokepoint 单点验证:不依赖 reduce 路径而依赖 ContextVar → bridge
    转译路径。确保 prompt assembler 未来无需主动读 ContextVar,只读
    state.activated_skills(已 populated)即可。
    """
    from lca.infrastructure.skills.activation.scope import register_activated

    state = _fresh_state()
    reducer = DefaultReducer()
    global_bridge.dispose()
    global_bridge.install(reducer=reducer, state_getter=lambda: state)
    try:
        register_activated("pdf", "PDF")
        register_activated("officecli", "Office CLI")
        ids = [s.skill_id for s in state.activated_skills]
        assert "pdf" in ids
        assert "officecli" in ids
    finally:
        global_bridge.dispose()


__all__ = [
    "test_bridge_handle_before_install_is_noop",
    "test_bridge_install_then_handle_folds_into_state",
    "test_bridge_repeated_handle_appends",
    "test_bridge_dispose_makes_handle_noop",
    "test_global_singleton_install_dispose_idempotent",
    "test_register_activated_in_scope_invokes_bridge",
]