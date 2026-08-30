from __future__ import annotations

import pytest

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.result import Result


def test_result_observation_metadata_requires_typed_identity() -> None:
    with pytest.raises(ValueError, match="source_total_steps must be an integer"):
        Result.from_observation(
            Observation(
                observation_id="obs-1",
                success=True,
                payload="ok",
                extra={"source_total_steps": "2"},
            ),
            "task-1",
        )
    with pytest.raises(ValueError, match="source_trace_id must be a non-empty string"):
        Result.from_observation(
            Observation(
                observation_id="obs-1", success=True, payload="ok", extra={"source_trace_id": 7}
            ),
            "task-1",
        )


def test_result_observation_metadata_accepts_valid_values() -> None:
    result = Result.from_observation(
        Observation(
            observation_id="obs-1",
            success=True,
            payload="ok",
            extra={"source_total_steps": 2, "source_trace_id": "trace-1"},
        ),
        "task-1",
    )
    assert result.total_steps == 2
    assert result.trace_id == "trace-1"
