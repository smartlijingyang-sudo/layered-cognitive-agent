from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.state import AgentState
from lca.layer2_runtime.runtime_loop import CognitiveRuntime


class _FailingStateStore:
    async def save(self, state: AgentState) -> str:
        del state
        raise OSError("state store unavailable")


@pytest.mark.asyncio
async def test_checkpoint_rolls_back_snapshot_when_state_store_save_fails() -> None:
    runtime: Any = object.__new__(CognitiveRuntime)
    runtime.state_store = _FailingStateStore()
    runtime.evaluate_control = lambda *args, **kwargs: None
    state = AgentState(
        trace_id="trace-checkpoint",
        task="checkpoint rollback",
        budget=create_budget(max_steps=3),
    )

    with pytest.raises(OSError, match="state store unavailable"):
        await runtime._checkpoint(state)

    assert state.checkpoints == []
