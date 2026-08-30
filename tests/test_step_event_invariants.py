from __future__ import annotations

import pytest

from lca.contracts.harness.events import StepEnded, StepStarted


@pytest.mark.parametrize("event_type", [StepStarted, StepEnded])
def test_step_events_reject_negative_coordinates(event_type: type[object]) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        event_type(turn=-1, step=0)


def test_step_started_accepts_zero_based_coordinates() -> None:
    event = StepStarted(turn=0, step=0)

    assert event.turn == 0
    assert event.step == 0
