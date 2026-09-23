"""ADR-0248 profile.json.runtime → RunContext.extra 透传测试。

验证 ``run_context_for_session`` 把 assistant 的 ``profile_runtime``
（即 ``profile.json.runtime``）中的声带/审查/唤醒键写入
``RunContext.extra``，使 runtime loop 能据此启用 gated 模式。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.plugins.transport.webserver.carrier.runs.lifecycle.run_context_factory import (
    run_context_for_session,
)


@dataclass
class _AgentRefStub:
    agent_id: str = "agt_test"
    name: str = "Test Agent"


@dataclass
class _SessionStub:
    agent: _AgentRefStub = field(default_factory=_AgentRefStub)
    prior_turns: tuple[ConversationTurn, ...] = field(default_factory=tuple)


def test_profile_runtime_vocal_mode_injected() -> None:
    session = _SessionStub()
    ctx = run_context_for_session(
        session,  # type: ignore[arg-type]
        profile_runtime={"vocal_mode": "gated", "max_steps": 10},
    )
    assert ctx.extra["agent_id"] == "agt_test"
    assert ctx.extra["vocal_mode"] == "gated"
    # 非 ADR-0248 键不透传（max_steps 仍走 Agent 构造，不进 RunContext）
    assert "max_steps" not in ctx.extra


def test_profile_runtime_auto_review_and_wake_source() -> None:
    session = _SessionStub()
    ctx = run_context_for_session(
        session,  # type: ignore[arg-type]
        profile_runtime={"auto_review_mode": "enforce", "wake_source": "routine"},
    )
    assert ctx.extra["auto_review_mode"] == "enforce"
    assert ctx.extra["wake_source"] == "routine"


def test_no_profile_runtime_keeps_default_extra() -> None:
    session = _SessionStub()
    ctx = run_context_for_session(session)  # type: ignore[arg-type]
    assert ctx.extra == {"agent_id": "agt_test", "agent_name": "Test Agent"}


def test_prior_turns_preserved() -> None:
    prior = (ConversationTurn(role="user", content="hi"),)
    session = _SessionStub(prior_turns=prior)
    ctx = run_context_for_session(
        session,  # type: ignore[arg-type]
        profile_runtime={"vocal_mode": "gated"},
    )
    assert ctx.prior_turns == prior
