"""say-do 门 fail-closed 回归（ADR-0260 §6；run_45fa85c1ee75）。

无记忆子系统、无注入回执时，写盘宣称必须被拒绝句替换，
而不是原样放行（旧 fail-open）。
"""
from __future__ import annotations

from types import SimpleNamespace

from lca.cognition.memory.acknowledgement import (
    _REFUSAL,
    guard_reply,
)


def test_claim_without_memory_or_receipt_is_refused():
    assert guard_reply("我记下了", None) == _REFUSAL
    assert guard_reply("改名叫大内管家：记下了", None) == _REFUSAL


def test_commissive_future_claim_is_refused():
    # run_45fa85c1ee75 的实际回复口径
    assert guard_reply("我先用记忆记录下来", None) == _REFUSAL
    assert guard_reply("我会记下你的偏好", None) == _REFUSAL


def test_non_claim_passes_through():
    assert guard_reply("好的，收到", None) == "好的，收到"
    assert guard_reply(None, None) is None


def test_spent_claim_right_allows_claim():
    runtime = SimpleNamespace(memory=SimpleNamespace(take_claim_right=lambda: object()))
    assert guard_reply("我记下了", runtime) == "我记下了"


def test_no_claim_right_refuses():
    runtime = SimpleNamespace(memory=SimpleNamespace(take_claim_right=lambda: None))
    assert guard_reply("我记下了", runtime) == _REFUSAL


def test_injected_receipt_path_still_works():
    receipt = SimpleNamespace(may_acknowledge=True)
    runtime = SimpleNamespace(memory_receipt=receipt)
    assert guard_reply("我记下了", runtime) == "我记下了"
    receipt_bad = SimpleNamespace(may_acknowledge=False)
    runtime_bad = SimpleNamespace(memory_receipt=receipt_bad)
    assert guard_reply("我记下了", runtime_bad) == _REFUSAL
