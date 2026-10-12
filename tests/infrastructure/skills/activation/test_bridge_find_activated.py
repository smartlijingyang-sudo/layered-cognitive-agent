"""SkillActivationReducerBridge.find_activated 的 bridge 层单元测试。

bridge 级别的兜底 seam：不经 ContextVar / resolve_skill_for_exec，直接验证
installed/uninstalled、by-id、by-name、tail 四种语义。
"""

from __future__ import annotations

from lca.contracts.models.core.policy.budget import Budget
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.infrastructure.skills.activation.bridge import SkillActivationReducerBridge
from lca.plugins.loop.reducer.plugin import DefaultReducer


def _fresh_state() -> AgentState:
    return AgentState(trace_id="t_bfa", task="x", budget=Budget())


def _installed_bridge(state: AgentState) -> SkillActivationReducerBridge:
    bridge = SkillActivationReducerBridge()
    bridge.install(reducer=DefaultReducer(), state_getter=lambda: state)
    return bridge


def _seed(state: AgentState, *pairs: tuple[str, str]) -> None:
    reducer = DefaultReducer()
    for skill_id, name in pairs:
        reducer.apply_activation(
            state, (ActivatedSkill(skill_id=skill_id, name=name),)
        )


def test_find_activated_uninstalled_returns_none() -> None:
    bridge = SkillActivationReducerBridge()
    assert bridge.find_activated("x") is None
    assert bridge.find_activated(None) is None


def test_find_activated_by_id_returns_latest() -> None:
    state = _fresh_state()
    _seed(state, ("s-a", "alpha"), ("s-b", "beta"), ("s-a", "alpha-v2"))
    bridge = _installed_bridge(state)
    found = bridge.find_activated("s-a")
    assert found is not None
    assert found.skill_id == "s-a"
    assert found.name == "alpha-v2"


def test_find_activated_by_name() -> None:
    state = _fresh_state()
    _seed(state, ("s-a", "alpha"), ("s-b", "beta"))
    bridge = _installed_bridge(state)
    found = bridge.find_activated("beta")
    assert found is not None
    assert found.skill_id == "s-b"


def test_find_activated_none_returns_tail() -> None:
    state = _fresh_state()
    _seed(state, ("s-a", "alpha"), ("s-b", "beta"))
    bridge = _installed_bridge(state)
    found = bridge.find_activated(None)
    assert found is not None
    assert found.skill_id == "s-b"


def test_find_activated_no_match_returns_none() -> None:
    state = _fresh_state()
    _seed(state, ("s-a", "alpha"))
    bridge = _installed_bridge(state)
    assert bridge.find_activated("nope") is None


def test_find_activated_empty_state_tail_returns_none() -> None:
    state = _fresh_state()
    bridge = _installed_bridge(state)
    assert bridge.find_activated(None) is None
    assert bridge.find_activated("s-a") is None
