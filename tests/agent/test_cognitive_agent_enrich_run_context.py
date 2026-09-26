"""Regression test for ADR-0244 multi-turn context preservation.

``CognitiveAgent._enrich_run_context`` rebuilds the ``RunContext`` when a
workspace deadline is present. The rebuilt context must carry ``prior_turns``
through, otherwise the runtime loop seeds no conversation history and every
turn looks like the first message (the run's model-visible request ends up
with a single user message).
"""

from __future__ import annotations

from unittest.mock import patch

from lca.agent.cognitive_agent import CognitiveAgent
from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.contracts.models.team.run.context import RunContext


def _workspace_with_deadline() -> object:
    class _Workspace:
        deadline = object()

    return _Workspace()


def test_enrich_run_context_preserves_prior_turns() -> None:
    """The deadline-enrichment branch must copy prior_turns into the new context."""
    ctx = RunContext(
        session_id="sess-1",
        prior_turns=(
            ConversationTurn(role="user", content="第一轮：我是架构师。"),
            ConversationTurn(role="assistant", content="好的，记住了。"),
        ),
    )
    with patch(
        "lca.agent.cognitive_agent.get_run_workspace",
        return_value=_workspace_with_deadline(),
    ):
        enriched = CognitiveAgent._enrich_run_context(ctx)

    assert enriched is not None
    assert enriched is not ctx
    assert [(t.role, t.content) for t in enriched.prior_turns] == [
        ("user", "第一轮：我是架构师。"),
        ("assistant", "好的，记住了。"),
    ]


def test_enrich_run_context_without_workspace_deadline_returns_same() -> None:
    """No workspace deadline means the original context (with prior_turns) is used."""
    ctx = RunContext(prior_turns=(ConversationTurn(role="user", content="第一轮"),))
    with patch(
        "lca.agent.cognitive_agent.get_run_workspace",
        return_value=None,
    ):
        enriched = CognitiveAgent._enrich_run_context(ctx)

    assert enriched is ctx


def test_enrich_run_context_with_existing_deadline_returns_same() -> None:
    """A context that already carries a deadline is not rebuilt."""
    deadline = object()
    ctx = RunContext(
        deadline=deadline, prior_turns=(ConversationTurn(role="user", content="第一轮"),)
    )
    with patch(
        "lca.agent.cognitive_agent.get_run_workspace",
        return_value=_workspace_with_deadline(),
    ):
        enriched = CognitiveAgent._enrich_run_context(ctx)

    assert enriched is ctx
