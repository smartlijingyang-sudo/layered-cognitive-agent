"""SimpleCritic partial batch reflection (ADR-0201 sibling)."""

from __future__ import annotations

from lca.cognition.brain.reasoner.critic import SimpleCritic
from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import OBS_TOOL_RESULTS
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.state.state import AgentState, Budget


def test_partial_batch_does_not_need_correction() -> None:
    obs = Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error="exit_code=127",
        extra={
            OBS_TOOL_RESULTS: [
                {
                    "call_id": "a",
                    "tool_name": "runCommand",
                    "observation": Observation(
                        observation_id=new_id("obs"),
                        success=False,
                        payload=None,
                        error="exit_code=127",
                    ),
                },
                {
                    "call_id": "b",
                    "tool_name": "executeCode",
                    "observation": Observation(
                        observation_id=new_id("obs"),
                        success=True,
                        payload={"stdout": "pdf text"},
                    ),
                },
            ],
        },
    )
    reflection = SimpleCritic()._evaluate(
        AgentState(trace_id="t", task="test", budget=Budget()),
        obs,
    )
    assert reflection.verdict == ReflectionVerdict.ON_TRACK
    assert "部分工具成功" in (reflection.lesson or "")


def test_all_failed_batch_still_needs_correction() -> None:
    obs = Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error="failed",
        extra={
            OBS_TOOL_RESULTS: [
                {
                    "tool_name": "runCommand",
                    "observation": Observation(
                        observation_id=new_id("obs"),
                        success=False,
                        payload=None,
                        error="a",
                    ),
                },
            ],
        },
    )
    reflection = SimpleCritic()._evaluate(
        AgentState(trace_id="t", task="test", budget=Budget()),
        obs,
    )
    assert reflection.verdict == ReflectionVerdict.NEEDS_CORRECTION
