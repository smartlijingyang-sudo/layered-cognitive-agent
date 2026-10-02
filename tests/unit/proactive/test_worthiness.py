# -*- coding: utf-8 -*-
"""WorthinessGate 决策矩阵单元测试（纯函数，无 IO）。

覆盖：原有决策矩阵（回归）+ ADR-0264 §4① 调用方声明交叉校验
（downgrade-only、request_ref 机械校验）——§5 T1。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from lca.cognition.proactive import decide
from lca.contracts.models.proactive import (
    DeliveryTarget,
    DeliveryTargetKind,
    ProactiveMessage,
    ProactiveRequest,
    ProactiveSource,
    VerdictKind,
)


def _req(**kw):
    base = dict(
        message=ProactiveMessage(
            id="m1",
            content="hello",
            source=ProactiveSource.MANUAL,
        ),
        target=DeliveryTarget(kind=DeliveryTargetKind.SESSION_APPEND, session_id="s1"),
        requested=False,
        declared=VerdictKind.DELIVER_CHAT,
        request_ref="req-1",
        known_request_refs=("req-1",),
    )
    base.update(kw)
    return ProactiveRequest(**base)


# ---------------- 原有矩阵（回归） ----------------


def test_requested_always_delivers_to_chat():
    v = decide(_req(requested=True))
    assert v.kind == VerdictKind.DELIVER_CHAT


def test_requested_wins_over_routine():
    v = decide(_req(requested=True, is_routine=True, is_novel=False))
    assert v.kind == VerdictKind.DELIVER_CHAT


def test_unrequested_routine_is_silent():
    v = decide(_req(is_routine=True))
    assert v.kind == VerdictKind.SILENT


def test_unrequested_not_novel_is_silent():
    v = decide(_req(is_novel=False))
    assert v.kind == VerdictKind.SILENT


def test_unrequested_worthy_pushes_to_chat():
    v = decide(_req(is_novel=True, worth_interrupting=True))
    assert v.kind == VerdictKind.DELIVER_CHAT


def test_unrequested_low_value_goes_quiet():
    v = decide(_req(is_novel=True, worth_interrupting=False))
    assert v.kind == VerdictKind.DELIVER_QUIET


def test_memory_dependent_without_source_degrades_and_annotates():
    msg = ProactiveMessage(
        id="m2",
        content="based on your memory",
        source=ProactiveSource.ROUTINE_CRON,
        requires_memory=True,
    )
    v = decide(_req(message=msg, has_memory_source=False))
    assert v.kind == VerdictKind.DELIVER_QUIET
    assert v.annotate_unretrieved is True


def test_memory_dependent_with_source_goes_quiet_without_annotation():
    msg = ProactiveMessage(
        id="m3",
        content="based on your memory",
        source=ProactiveSource.ROUTINE_CRON,
        requires_memory=True,
    )
    v = decide(_req(message=msg, has_memory_source=True))
    assert v.kind == VerdictKind.DELIVER_QUIET
    assert v.annotate_unretrieved is False


def test_credential_api_key_rejected():
    msg = ProactiveMessage(
        id="m4",
        content="your api_key: sk-abc123xyz",
        source=ProactiveSource.MANUAL,
    )
    v = decide(_req(message=msg, requested=True))
    assert v.kind == VerdictKind.REJECTED


def test_credential_bearer_rejected():
    msg = ProactiveMessage(
        id="m5",
        content="token Bearer abcdef123456",
        source=ProactiveSource.MANUAL,
    )
    v = decide(_req(message=msg, requested=True))
    assert v.kind == VerdictKind.REJECTED


def test_credential_password_rejected():
    msg = ProactiveMessage(
        id="m6",
        content="password= hunter2secret",
        source=ProactiveSource.MANUAL,
    )
    v = decide(_req(message=msg, requested=True))
    assert v.kind == VerdictKind.REJECTED


def test_benign_text_not_rejected():
    v = decide(_req(requested=True))
    assert v.kind == VerdictKind.DELIVER_CHAT


def test_verdict_carries_reason():
    v = decide(_req(requested=True))
    assert v.reason.strip() != ""


# ---------------- T1：调用方声明交叉校验 ----------------


def test_declared_chat_downgraded_when_request_ref_missing():
    """T1：声明 DELIVER_CHAT，但 request_ref 缺失 → 按未要求处理，
    gate 证据不足 → 降级为 DELIVER_QUIET。"""
    v = decide(_req(requested=True, request_ref=None, known_request_refs=()))
    assert v.kind == VerdictKind.DELIVER_QUIET
    assert "降级" in v.reason
    assert "request_ref" in v.reason


def test_declared_chat_downgraded_when_request_ref_forged():
    """T1：request_ref 伪造（不在背书集合中）→ 按未要求处理 → 降级。"""
    v = decide(
        _req(requested=True, request_ref="forged-ref", known_request_refs=("req-1",))
    )
    assert v.kind == VerdictKind.DELIVER_QUIET
    assert "request_ref" in v.reason


def test_unverified_requested_with_no_novelty_is_silent():
    """T1：request_ref 缺失 + 无新信息 → SILENT（已验证的 requested 会是 CHAT）。"""
    v = decide(
        _req(requested=True, request_ref=None, known_request_refs=(), is_novel=False)
    )
    assert v.kind == VerdictKind.SILENT


def test_gate_never_upgrades_declared_quiet():
    """T1：downgrade-only —— 即使 requested 已验证（gate 自有判断为 CHAT），
    调用方声明 QUIET 也不被升级。"""
    v = decide(_req(requested=True, declared=VerdictKind.DELIVER_QUIET))
    assert v.kind == VerdictKind.DELIVER_QUIET
    assert "不升级" in v.reason


def test_gate_never_upgrades_declared_silent():
    v = decide(
        _req(requested=True, declared=VerdictKind.SILENT, worth_interrupting=True)
    )
    assert v.kind == VerdictKind.SILENT


def test_credential_rejected_beats_verified_requested():
    """T1：凭证命中 + 已验证的 requested 冲突 → REJECTED 优先（最高抑制）。"""
    msg = ProactiveMessage(
        id="m9",
        content="api_key: sk-live-12345678",
        source=ProactiveSource.MANUAL,
    )
    v = decide(_req(message=msg, requested=True, declared=VerdictKind.DELIVER_CHAT))
    assert v.kind == VerdictKind.REJECTED


def test_declared_rejected_is_forbidden_by_contract():
    """调用方无权声明 REJECTED：那是 gate 专用的抑制裁决。"""
    with pytest.raises(Exception):
        _req(declared=VerdictKind.REJECTED)


def test_verified_requested_ref_recorded_in_reason():
    v = decide(_req(requested=True))
    assert "req-1" in v.reason
