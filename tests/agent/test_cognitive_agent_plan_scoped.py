"""RA-098: the plan_ref conditional scope lives in one seam (``_plan_scoped``).

run() and resume() used to each carry a verbatim 12-line
``if self._plan_ref: with plan_ref_scope(...)`` block. The conditional now
lives in ``CognitiveAgent._plan_scoped``; these tests pin its two behaviors:
bind the scope when a plan_ref is set, passthrough when it is not.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lca.agent.cognitive_agent import CognitiveAgent
from lca.contracts.models.observability.plan.ref import get_current_plan_ref


def _agent(plan_ref: str = "") -> CognitiveAgent:
    return CognitiveAgent(
        runtime=MagicMock(),
        role_profile=MagicMock(),
        observability=MagicMock(),
        plan_ref=plan_ref,
    )


def test_plan_scoped_binds_plan_ref_when_set() -> None:
    agent = _agent("plan-123")
    with agent._plan_scoped():
        assert get_current_plan_ref() == "plan-123"
    # The scope resets on exit — no leak into the ambient context.
    assert get_current_plan_ref() == ""


def test_plan_scoped_is_passthrough_when_unset() -> None:
    agent = _agent()
    with agent._plan_scoped():
        assert get_current_plan_ref() == ""
