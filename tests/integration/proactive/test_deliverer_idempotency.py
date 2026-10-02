# -*- coding: utf-8 -*-
"""投递层幂等集成测试（ADR-0264 §4②，§5 T3）。

同一 (session_id, proactive_id) 投递两次 → session 里只出现一次；
含"崩溃后重跑"场景：去重状态持久化，新实例 + 同一 state_dir 依然有效。
用真实 SessionStore + 真实文件去重，不 mock 写路径。
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from lca.contracts.models.proactive import (
    DeliveryTarget,
    DeliveryTargetKind,
    ProactiveMessage,
    ProactiveSource,
)
from lca.infrastructure.proactive import ProactiveDeliverer
from lca.plugins.session.runtime.store.store import SessionStore


def _fixture(tmp: Path):
    store = SessionStore()
    deliverer = ProactiveDeliverer(store, state_dir=tmp / "state")
    return store, deliverer


def _msg(mid="m-dup", content="hello"):
    return ProactiveMessage(id=mid, content=content, source=ProactiveSource.MANUAL)


def _target(sid="sess-dup"):
    return DeliveryTarget(kind=DeliveryTargetKind.SESSION_APPEND, session_id=sid)


def _proactive_events(store, sid):
    session = store.get(sid)
    assert session is not None
    return [e for e in session._log if e.type == "surface/assistant_message"]


def test_same_key_delivered_twice_session_has_one():
    """T3：同一 key 投递两次，session 里只出现一次，第二次回执 duplicate。"""
    tmp = Path(tempfile.mkdtemp())
    store, d = _fixture(tmp)
    msg, target = _msg(), _target()

    r1 = d.deliver(msg, target)
    assert r1["delivered"] is True
    assert r1.get("duplicate") is not True

    r2 = d.deliver(msg, target)
    assert r2["delivered"] is False
    assert r2["duplicate"] is True

    assert len(_proactive_events(store, "sess-dup")) == 1


def test_crash_restart_still_idempotent():
    """T3 崩溃后重跑：新 deliverer 实例 + 同一 state_dir，去重状态持久化有效。"""
    tmp = Path(tempfile.mkdtemp())
    store, d1 = _fixture(tmp)
    msg, target = _msg(), _target()
    d1.deliver(msg, target)

    # 去重状态确实落盘
    assert (tmp / "state" / "proactive_delivered.json").exists()

    # 模拟崩溃：全新实例（内存状态丢失），同一 state_dir
    d2 = ProactiveDeliverer(store, state_dir=tmp / "state")
    r = d2.deliver(msg, target)
    assert r["duplicate"] is True
    assert len(_proactive_events(store, "sess-dup")) == 1


def test_different_proactive_id_not_deduped():
    """不同 proactive_id 不误杀。"""
    tmp = Path(tempfile.mkdtemp())
    store, d = _fixture(tmp)
    target = _target()
    d.deliver(_msg(mid="m-a"), target)
    r = d.deliver(_msg(mid="m-b"), target)
    assert r["delivered"] is True
    assert len(_proactive_events(store, "sess-dup")) == 2


def test_same_proactive_id_different_session_not_deduped():
    """key 是 (session_id, proactive_id) 二元组：换 session 不误杀。"""
    tmp = Path(tempfile.mkdtemp())
    store, d = _fixture(tmp)
    d.deliver(_msg(mid="m-x"), _target(sid="sess-1"))
    r = d.deliver(_msg(mid="m-x"), _target(sid="sess-2"))
    assert r["delivered"] is True
    assert len(_proactive_events(store, "sess-1")) == 1
    assert len(_proactive_events(store, "sess-2")) == 1


def test_failed_append_not_marked_allows_retry():
    """append 抛错时不 mark：调用方可重试，重试成功后才去重。"""
    tmp = Path(tempfile.mkdtemp())

    class BrokenStore:
        def get(self, session_id):
            raise RuntimeError("store exploded")

        def create(self, session_id=None):
            raise RuntimeError("store exploded")

    d = ProactiveDeliverer(BrokenStore(), state_dir=tmp / "state")
    msg, target = _msg(), _target()
    try:
        d.deliver(msg, target)
        raise AssertionError("should have raised")
    except RuntimeError:
        pass
    # 未 mark：换好 store 重试应成功投递（而非被误判 duplicate）
    store = SessionStore()
    d2 = ProactiveDeliverer(store, state_dir=tmp / "state")
    r = d2.deliver(msg, target)
    assert r["delivered"] is True
    assert len(_proactive_events(store, "sess-dup")) == 1


def test_dedup_store_bounded_eviction():
    """有界：超 max_entries 淘汰最老。"""
    tmp = Path(tempfile.mkdtemp())
    store = SessionStore()
    d = ProactiveDeliverer(store, state_dir=tmp / "state", dedup_max_entries=2)
    target = _target()
    d.deliver(_msg(mid="m-1"), target)
    d.deliver(_msg(mid="m-2"), target)
    d.deliver(_msg(mid="m-3"), target)
    # m-1 被淘汰：再次投递不再是 duplicate（会重新 append）
    r = d.deliver(_msg(mid="m-1"), target)
    assert r["delivered"] is True
    assert len(_proactive_events(store, "sess-dup")) == 4
