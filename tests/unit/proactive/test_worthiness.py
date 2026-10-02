# -*- coding: utf-8 -*-
"""WorthinessGate 决策矩阵单元测试（纯函数，无 IO）。"""

import sys

sys.path.insert(0, "/tmp/proactive-1")

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
    )
    base.update(kw)
    return ProactiveRequest(**base)


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
