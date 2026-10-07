from __future__ import annotations

import pytest

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.result import Result


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


def test_result_observation_missing_trace_id_generates_id() -> None:
    """回归锁(2bb3ceefc):source_trace_id 缺席 → 自动生成 trace id,不许为 None。

    e51902b07 误判把 ``else: trace_id = raw_trace_id`` 的 else 拿掉后,
    ``trace_id=new_id("trace")`` 被 dedent 的赋值覆盖为 None。
    """
    result = Result.from_observation(
        Observation(
            observation_id="obs-1",
            success=True,
            payload="ok",
            extra={},
        ),
        "task-1",
    )
    assert isinstance(result.trace_id, str)
    assert result.trace_id.startswith("trace_")
