from __future__ import annotations

import pytest

from lca.contracts.harness.collaboration.handoff import AgentHandoff


def test_handoff_requires_distinct_owners() -> None:
    handoff = AgentHandoff("h1", "task-1", "lead", "analyst", "checkpoint://1")

    assert handoff.to_agent == "analyst"


def test_handoff_rejects_same_owner() -> None:
    with pytest.raises(ValueError, match="distinct"):
        AgentHandoff("h1", "task-1", "lead", "lead", "checkpoint://1")
