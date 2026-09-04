"""AgentStateProjection 的 checkpoint status wire 值回归。

`_parse_status` 把 ``session.checkpoint.v1`` 的 wire 词表折叠成
``TaskStatus``;``view()`` 再以 ``status.value`` 输出。两端字符串必须
逐字节稳定(生命周期值 + ``input_required`` 拼写别名)。
"""

from __future__ import annotations

import pytest

from lca.contracts.harness.tasks.session import SessionEvent
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.harness.projection.agent_state import AgentStateProjection


def _checkpoint(status: str) -> SessionEvent:
    return SessionEvent(
        type="session.checkpoint.v1",
        seq=1,
        time=0,
        data={"status": status},
        session_id="run-test",
    )


@pytest.mark.parametrize(
    ("wire_status", "expected"),
    [
        ("working", TaskStatus.WORKING),
        ("completed", TaskStatus.COMPLETED),
        ("failed", TaskStatus.FAILED),
        ("canceled", TaskStatus.CANCELED),
        ("paused", TaskStatus.PAUSED),
        ("input_required", TaskStatus.INPUT_REQUIRED),
        ("waiting_input", TaskStatus.INPUT_REQUIRED),
        ("unknown-status", TaskStatus.WORKING),
    ],
)
def test_checkpoint_status_wire_values(wire_status: str, expected: TaskStatus) -> None:
    projection = AgentStateProjection()
    state = projection.apply(projection.init(), _checkpoint(wire_status))
    assert state.status is expected
    assert projection.view(state)["status"] == expected.value
