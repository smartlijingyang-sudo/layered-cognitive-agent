from __future__ import annotations

from types import SimpleNamespace

import pytest

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.declarative_phase_graph import PhaseInput
from lca.plugins.control_contributions.standard import StandardControlContribution


@pytest.mark.asyncio
async def test_standard_control_denies_tool_action_without_a_call() -> None:
    decision = Decision(
        decision_id="decision:malformed-tool",
        action_type=ActionType.USE_TOOL,
        rationale="missing call",
        confidence=1.0,
    )
    context = SimpleNamespace(
        node_ref="act.main",
        state=AgentState(trace_id="trace:control", task="control", budget=create_budget()),
        artifacts={"think": decision},
    )

    outcome = await StandardControlContribution().execute(context, PhaseInput())

    assert outcome.payload["verdict"] == "deny"
    assert "tool call" in outcome.payload["reason"]
