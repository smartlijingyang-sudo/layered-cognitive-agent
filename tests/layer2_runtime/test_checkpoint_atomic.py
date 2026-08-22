from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.atoms.enums import SnapshotReason
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.declarative_phase_graph import PhaseRunCursor
from lca.layer2_runtime.declarative_runtime import DeclarativeRuntimeDriver


class _FailingStateStore:
    async def save(self, state: AgentState) -> str:
        del state
        raise OSError("state store unavailable")


@pytest.mark.asyncio
async def test_checkpoint_rolls_back_snapshot_when_state_store_save_fails() -> None:
    driver: Any = object.__new__(DeclarativeRuntimeDriver)
    driver._state_store = _FailingStateStore()
    state = AgentState(
        trace_id="trace-checkpoint",
        task="checkpoint rollback",
        budget=create_budget(max_steps=3),
    )

    cursor = PhaseRunCursor(plan_ref="plan:test", node_id="reflect.main")
    with pytest.raises(OSError, match="state store unavailable"):
        await driver._save_checkpoint(state, cursor=cursor, reason=SnapshotReason.ON_ERROR)

    assert state.checkpoints == []
