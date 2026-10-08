"""RA-046: Agent.run(None) must fail loud at the entry, not deep in the runtime."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lca.agent.cognitive_agent import CognitiveAgent


def _agent() -> CognitiveAgent:
    # The None-task guard is the first statement of run(); none of these
    # collaborators are touched on that path.
    return CognitiveAgent(
        runtime=MagicMock(),
        role_profile=MagicMock(),
        observability=MagicMock(),
    )


async def test_run_none_task_raises_type_error() -> None:
    """A None task used to travel into the runtime and die with an obscure
    TypeError inside objective_preview (None[:N])."""
    with pytest.raises(TypeError, match="must be str"):
        await _agent().run(None)  # type: ignore[arg-type]
