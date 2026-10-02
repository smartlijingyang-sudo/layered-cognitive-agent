# -*- coding: utf-8 -*-
"""ProactivePolicy 政策层单元测试（纯函数，无 IO）。

覆盖 ADR-0264 §4③④：全局总开关（gate 为唯一卡点）、quiet hours
上限 DELIVER_QUIET（消息照投递，只是不打断）。
"""

import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

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
from lca.contracts.models.proactive.policy import ProactivePolicy

SH = ZoneInfo("Asia/Shanghai")


def _req(**kw):
    base = dict(
        message=ProactiveMessage(
            id="m1", content="hello", source=ProactiveSource.MANUAL
        ),
        target=DeliveryTarget(
            kind=DeliveryTargetKind.SESSION_APPEND, session_id="s1"
        ),
        requested=True,
        declared=VerdictKind.DELIVER_CHAT,
        request_ref="req-1",
        known_request_refs=("req-1",),
    )
    base.update(kw)
    return ProactiveRequest(**base)


def _at(hour, minute=0):
    return datetime(2026, 10, 2, hour, minute, tzinfo=SH)


# ---------------- 契约 ----------------


def test_policy_defaults():
    p = ProactivePolicy()
    assert p.enabled is True
    assert p.quiet_hours_start == time(22, 0)
    assert p.quiet_hours_end == time(8, 0)
    assert p.timezone == "Asia/Shanghai"


def test_policy_is_frozen():
    p = ProactivePolicy()
    with pytest.raises(Exception):
        p.enabled = False


def test_no_policy_means_matrix_only():
    # 不传 policy 时保持旧调用兼容：verified requested -> CHAT
    v = decide(_req(requested=True))
    assert v.kind == VerdictKind.DELIVER_CHAT


# ---------------- 总开关 ----------------


def test_disabled_policy_forces_silent():
    v = decide(
        _req(requested=True),
        policy=ProactivePolicy(enabled=False),
        now=_at(10),
    )
    assert v.kind == VerdictKind.SILENT
    assert "enabled=False" in v.reason


def test_disabled_policy_preserves_credential_rejection():
    """总开关不掩盖凭证红线：REJECTED 照样是 REJECTED（调用方照记 warning）。"""
    msg = ProactiveMessage(
        id="m-cred", content="password= hunter2", source=ProactiveSource.MANUAL
    )
    v = decide(
        _req(message=msg, requested=True),
        policy=ProactivePolicy(enabled=False),
        now=_at(10),
    )
    assert v.kind == VerdictKind.REJECTED


# ---------------- quiet hours ----------------


def test_quiet_hours_caps_chat_to_quiet():
    v = decide(_req(requested=True), policy=ProactivePolicy(), now=_at(23))
    assert v.kind == VerdictKind.DELIVER_QUIET
    assert "quiet hours" in v.reason


def test_quiet_hours_passes_through_in_daytime():
    v = decide(_req(requested=True), policy=ProactivePolicy(), now=_at(10))
    assert v.kind == VerdictKind.DELIVER_CHAT


def test_quiet_hours_boundaries():
    p = ProactivePolicy()
    assert decide(_req(requested=True), policy=p, now=_at(21, 59)).kind == VerdictKind.DELIVER_CHAT
    assert decide(_req(requested=True), policy=p, now=_at(22, 0)).kind == VerdictKind.DELIVER_QUIET
    assert decide(_req(requested=True), policy=p, now=_at(7, 59)).kind == VerdictKind.DELIVER_QUIET
    # 止（不含）：08:00 已出 quiet hours
    assert decide(_req(requested=True), policy=p, now=_at(8, 0)).kind == VerdictKind.DELIVER_CHAT


def test_quiet_hours_keeps_silent_silent():
    """quiet hours 不把 SILENT 抬成 QUIET：上限只 cap，不托底。"""
    v = decide(
        _req(requested=False, is_routine=True),
        policy=ProactivePolicy(),
        now=_at(23),
    )
    assert v.kind == VerdictKind.SILENT


def test_quiet_hours_keeps_quiet_quiet():
    v = decide(
        _req(requested=False, is_novel=True),
        policy=ProactivePolicy(),
        now=_at(23),
    )
    assert v.kind == VerdictKind.DELIVER_QUIET


def test_custom_quiet_window_no_midnight_wrap():
    p = ProactivePolicy(
        quiet_hours_start=time(13, 0), quiet_hours_end=time(14, 0)
    )
    assert decide(_req(requested=True), policy=p, now=_at(13, 30)).kind == VerdictKind.DELIVER_QUIET
    assert decide(_req(requested=True), policy=p, now=_at(15, 0)).kind == VerdictKind.DELIVER_CHAT


def test_same_start_end_means_no_quiet_hours():
    p = ProactivePolicy(
        quiet_hours_start=time(0, 0), quiet_hours_end=time(0, 0)
    )
    assert decide(_req(requested=True), policy=p, now=_at(3)).kind == VerdictKind.DELIVER_CHAT


def test_invalid_timezone_does_not_crash_tick():
    """时区配错：记 warning、跳过限流，不炸 tick（fail-open 于子功能）。"""
    p = ProactivePolicy(timezone="Mars/Olympus_Mons")
    v = decide(_req(requested=True), policy=p, now=_at(23))
    assert v.kind == VerdictKind.DELIVER_CHAT


def test_naive_now_assumed_policy_tz():
    p = ProactivePolicy()
    v = decide(
        _req(requested=True),
        policy=p,
        now=datetime(2026, 10, 2, 23, 0),  # naive → 按 policy 时区解释
    )
    assert v.kind == VerdictKind.DELIVER_QUIET
