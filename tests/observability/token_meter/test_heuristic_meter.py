"""Wave 2: TokenMeter 确定性 fold（验收 #9 / #14 附带）。"""

from __future__ import annotations

from lca.plugins.session.runtime.session import Session
from lca.plugins.session.token_meter.token_meter import HeuristicTokenMeter, estimate_text_tokens
from lca_kernel.events.fold import SURFACE_ASSISTANT_TYPE, SURFACE_USER_TYPE


def test_estimate_text_tokens_deterministic() -> None:
    assert estimate_text_tokens("abcd") == 1
    assert estimate_text_tokens("hello world") == 3


def test_measure_same_log_twice_identical() -> None:
    session = Session("meter_1")
    session.append(
        SURFACE_USER_TYPE,
        {"content": "hello"},
        surface_op="append",
    )
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {"message": {"role": "assistant", "content": "hi there"}},
        surface_op="append",
    )
    meter = HeuristicTokenMeter()
    a = meter.measure(session)
    b = meter.measure(session)
    assert a == b
    assert a.surface_tokens > 0
    assert a.log_revision == 2


def test_usage_anchor_only_when_header_matches() -> None:
    session = Session("meter_2")
    session.append("model.completed.v1", {"usage": {"total_tokens": 999}})
    meter = HeuristicTokenMeter()
    mismatched = meter.measure(session, header={"config": {"model": "other"}})
    assert mismatched.baseline_kind == "estimated"
    assert mismatched.baseline == 0
