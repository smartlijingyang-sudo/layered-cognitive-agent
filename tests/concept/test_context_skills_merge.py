"""context.skills.merge 从 agent_state 读激活状态的回归测试。

run_b9cf3095caed 中 ``<activated_skills>`` 始终为"（无）"：节点声明
``inputs: [manifest, task, state]``，但生产 port seed 只注入 tools/bindings，
state 端口为 None。修复后应从 ``context.node_config["agent_state"]`` 兜底读取。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from lca.contracts.models.core.policy.budget import Budget
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.nodes.concept.context_compose.skills import ContextSkillsMergeExecutor


def _fresh_state() -> AgentState:
    return AgentState(trace_id="t_csm", task="创建助理", budget=Budget())


def test_context_skills_merge_reads_activated_skills_from_agent_state() -> None:
    """state 端口缺失时从 agent_state 兜底，ReasonerContext 携带激活列表。"""
    state = _fresh_state()
    state.activated_skills.append(
        ActivatedSkill(skill_id="create-assistant", name="create-assistant")
    )
    executor = ContextSkillsMergeExecutor()
    ctx = SimpleNamespace(node_config={"agent_state": state})
    inp = SimpleNamespace(port_values={})
    out = asyncio.run(executor.node_execute(ctx, inp))
    context = out.port_values["context"]
    assert [s.skill_id for s in context.activated_skills] == ["create-assistant"]


def test_context_skills_merge_state_port_still_wins_when_present() -> None:
    """state 端口有值时仍以端口为准（不回退 agent_state）。"""
    from lca.contracts.protocols.declarative.declarative_1.ports import PortName

    port_state = _fresh_state()
    port_state.activated_skills.append(ActivatedSkill(skill_id="port-skill", name="Port"))
    agent_state = _fresh_state()
    agent_state.activated_skills.append(ActivatedSkill(skill_id="agent-skill", name="Agent"))
    executor = ContextSkillsMergeExecutor()
    ctx = SimpleNamespace(node_config={"agent_state": agent_state})
    inp = SimpleNamespace(port_values={PortName("state"): port_state})
    out = asyncio.run(executor.node_execute(ctx, inp))
    context = out.port_values["context"]
    assert [s.skill_id for s in context.activated_skills] == ["port-skill"]
