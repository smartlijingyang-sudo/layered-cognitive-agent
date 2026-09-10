"""M2/M3 — NodeEnter / NodeExit / NodeException schema contract tests.

核心承诺: inputs / outputs 是完整 payload,不是 digest。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.observability.observation import (
    NodeEnter,
    NodeException,
    NodeExit,
)


def test_node_enter_inputs_full_payload_no_digest() -> None:
    ne = NodeEnter(
        run_id="r1",
        node_id="think.main",
        phase="think",
        inputs={"context": {"user_text": "hi"}, "assembled_manifest": ["a", "b"]},
        entered_at="t",
    )
    assert ne.inputs["context"]["user_text"] == "hi"
    assert "assembled_manifest" in ne.inputs
    assert ne.depth == 0
    assert ne.visit_count == 1


def test_node_exit_outputs_full_payload_no_digest() -> None:
    nx = NodeExit(
        run_id="r1",
        node_id="act.main",
        phase="act",
        outputs={"decision": {"action_type": "use_TOOL", "payload": {"x": 1}}},
        exit_status="success",
        elapsed_ms=120,
        exited_at="t",
    )
    assert nx.outputs["decision"]["action_type"] == "use_TOOL"
    assert nx.outputs["decision"]["payload"]["x"] == 1


def test_node_exit_exception_full_traceback() -> None:
    exc = NodeException(
        exception_class="RuntimeError",
        exception_message="action type is not authorized",
        traceback_text="Traceback ... RuntimeError: ...",
        source_location="act_safe_boundary/plugin.py:42",
    )
    nx = NodeExit(
        run_id="r1",
        node_id="act.main",
        phase="act",
        exit_status="error",
        exception=exc,
        exited_at="t",
    )
    assert nx.exception is not None
    assert nx.exception.source_location == "act_safe_boundary/plugin.py:42"


def test_node_enter_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        NodeEnter(
            run_id="r",
            node_id="x",
            phase="p",
            inputs={},
            entered_at="t",
            unknown="x",  # type: ignore[call-arg]
        )


def test_node_exit_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        NodeExit(
            run_id="r",
            node_id="x",
            phase="p",
            exit_status="success",
            exited_at="t",
            unknown="x",  # type: ignore[call-arg]
        )
