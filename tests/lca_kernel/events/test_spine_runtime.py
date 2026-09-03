"""spine_runtime helpers 测试（ADR-0181 PR-2 提取层）。"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from lca_kernel.events import EventRef
from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.spine_runtime import (
    SpineChain,
    SpineChainContext,
    SpineClock,
    SpineEventRecord,
    SpineStream,
    default_chain_path,
    is_spine_event,
)

# ── is_spine_event ───────────────────────────────────────────────────────


def test_is_spine_event_true_for_spine_payload() -> None:
    p = SpineEventPayload(execution_point="brain.perceive.start")
    assert is_spine_event(p) is True


def test_is_spine_event_false_for_other_payload() -> None:
    class NotSpine:
        pass

    assert is_spine_event(NotSpine()) is False


# ── SpineClock ──────────────────────────────────────────────────────────


def test_clock_freeze() -> None:
    fixed = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    SpineClock.freeze(fixed)
    try:
        assert SpineClock.now() == fixed
        assert SpineClock.now_iso() == "2026-09-03T12:00:00+00:00"
    finally:
        SpineClock.freeze(None)


def test_clock_unfrozen_returns_wall_clock() -> None:
    SpineClock.freeze(None)
    a = SpineClock.now()
    b = SpineClock.now()
    # 墙钟;不能保证严格差,但必须有时区且非 None
    assert a.tzinfo is not None
    assert b.tzinfo is not None


# ── SpineChain ──────────────────────────────────────────────────────────


def test_chain_two_records_form_hash_chain() -> None:
    """盖章 5: 2 record prev_event_hash 链 + event_hash 链。"""
    r1 = {"execution_point": "a", "channel": "fact", "payload": {}, "event_id": "e1"}
    r2 = {"execution_point": "b", "channel": "fact", "payload": {}, "event_id": "e2"}
    c1 = SpineChain.causality_id(r1)
    h1 = SpineChain.next_hash(None, c1)
    c2 = SpineChain.causality_id(r2)
    h2 = SpineChain.next_hash(h1, c2)
    assert h1 != h2
    assert c1 != c2


# ── SpineEventRecord ────────────────────────────────────────────────────


def _build_payload() -> SpineEventPayload:
    return SpineEventPayload(
        category=Category.SPINE_COGNITION_BRAIN_PERCEIVE_START,
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": "s1"},
    )


def test_record_build_without_chain() -> None:
    """无 chain = causation_id / prev_event_hash / event_hash 字段存在但为 None。

    PR-2 契约：字段一律输出（值可 None），下游消费者 dict.get() / d["k"] 行为一致。
    """
    p = _build_payload()
    ref = EventRef(
        event_id="e1",
        category=p.category.value,
        trace_id="t1",
        ts=0.0,
        persisted=False,
        subscriber_count=0,
    )
    rec = SpineEventRecord.build(p, ref)
    d = rec.to_dict()
    assert d["event_id"] == "e1"
    assert d["category"] == "spine.cognition.brain.perceive.start"
    assert d["execution_point"] == "brain.perceive.start"
    assert d["channel"] == "fact"
    assert d["payload"] == {"state_id": "s1"}
    assert d["causation_id"] is None
    assert d["prev_event_hash"] is None
    assert d["event_hash"] is None


def test_record_build_with_chain_from_start() -> None:
    """chain 起点（prev_hash=None）必须算 event_hash（不是 None）。"""
    p = _build_payload()
    ref = EventRef(
        event_id="e1",
        category=p.category.value,
        trace_id="t1",
        ts=0.0,
        persisted=False,
        subscriber_count=0,
    )
    rec = SpineEventRecord.build(p, ref, chain=SpineChainContext(prev_hash=None))
    d = rec.to_dict()
    assert d["prev_event_hash"] is None
    assert d["causation_id"] is not None
    assert d["event_hash"] is not None
    assert d["causation_id"] != d["event_hash"]


def test_record_build_with_chain_from_prev() -> None:
    """chain 中段（prev_hash=sha256:abc）必须继承 prev + 算新 hash。"""
    p = _build_payload()
    ref = EventRef(
        event_id="e1",
        category=p.category.value,
        trace_id="t1",
        ts=0.0,
        persisted=False,
        subscriber_count=0,
    )
    rec = SpineEventRecord.build(p, ref, chain=SpineChainContext(prev_hash="sha256:abc"))
    d = rec.to_dict()
    assert d["prev_event_hash"] == "sha256:abc"
    assert d["causation_id"] is not None
    assert d["event_hash"] is not None
    assert d["causation_id"] != d["event_hash"]
    assert d["event_hash"] != "sha256:abc"


# ── SpineStream ─────────────────────────────────────────────────────────


def test_stream_writes_to_injected() -> None:
    buf = io.StringIO()
    s = SpineStream(default=buf)
    s.write("hello")
    s.write("world")
    assert buf.getvalue() == "hello\nworld\n"


# ── default_chain_path ──────────────────────────────────────────────────


def test_default_chain_path_uses_env(tmp_path: Path) -> None:
    custom = tmp_path / "chain.jsonl"
    with patch.dict("os.environ", {"LCA_SPINE_CHAIN_PATH": str(custom)}):
        assert default_chain_path() == custom


def test_default_chain_path_falls_back_to_tempdir() -> None:
    with patch.dict("os.environ", {}, clear=False):
        os.environ.pop("LCA_SPINE_CHAIN_PATH", None)
        p = default_chain_path()
        # 一定是 Path
        assert isinstance(p, Path)
        assert p.suffix == ".jsonl"
