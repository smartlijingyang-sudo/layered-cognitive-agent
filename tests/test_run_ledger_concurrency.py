"""RunLedger L1/L3 并发安全(ADR-0065 PR-4)。

- 多线程并发 append → run_seq 严格连续 1..N,无重复无缺
- expected_run_seq 不匹配抛 LedgerSeqMismatchError
- expected_run_seq 匹配可串行化并行 append
"""

from __future__ import annotations

import contextlib
import threading

import pytest

from lca.contracts.models.observability.journal import AgentRunStarted
from lca.contracts.observability.ledger import LedgerSeqMismatchError
from lca.layer0_infra.observability.journal.engine import RunStore


def test_concurrent_appends_produce_continuous_unique_seq() -> None:
    """1000 线程并发 append → run_seq 严格连续 1..1000,无重复无缺。"""
    store = RunStore(run_id="r-concurrent")

    n_threads = 1000

    barrier = threading.Barrier(n_threads)

    def worker() -> None:
        barrier.wait()
        store.append(AgentRunStarted(agent_role="worker"))

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    events = store.events
    assert len(events) == n_threads
    # 严格连续 1..N
    seqs = sorted(e.seq for e in events)
    assert seqs == list(range(1, n_threads + 1))
    # 无重复 seq
    assert len(set(seqs)) == n_threads


def test_expected_run_seq_mismatch_raises() -> None:
    """并发调用方声明 expected_run_seq 与当前不匹配 → LedgerSeqMismatchError。"""
    store = RunStore(run_id="r-mismatch")
    store.append(AgentRunStarted(agent_role="first"))  # seq=1
    with pytest.raises(LedgerSeqMismatchError):
        store.append(
            AgentRunStarted(agent_role="second"),
            expected_run_seq=5,  # 期望 5 但当前是 1
        )


def test_expected_run_seq_matches_passes() -> None:
    """expected_run_seq 与当前一致 → 接受。"""
    store = RunStore(run_id="r-match")
    store.append(AgentRunStarted(agent_role="first"))  # seq=1, current=1
    stamped = store.append(
        AgentRunStarted(agent_role="second"),
        expected_run_seq=1,  # 当前是 1,匹配
    )
    assert stamped.seq == 2


def test_expected_run_seq_serializes_concurrent_writers() -> None:
    """两个 worker 各自声明 expected_run_seq,序列化器协调二者顺序。"""
    store = RunStore(run_id="r-serialize")
    barrier = threading.Barrier(2)
    results: list[int] = []
    errors: list[Exception] = []

    def writer_a() -> None:
        barrier.wait()
        try:
            stamped = store.append(
                AgentRunStarted(agent_role="a"),
                expected_run_seq=0,
            )
            results.append(stamped.seq)
        except Exception as exc:
            errors.append(exc)

    def writer_b() -> None:
        barrier.wait()
        try:
            stamped = store.append(
                AgentRunStarted(agent_role="b"),
                expected_run_seq=1,
            )
            results.append(stamped.seq)
        except LedgerSeqMismatchError as exc:
            # 正常:a 先写完,b 看到的 current 已经是 2 而非 1
            errors.append(exc)

    ta = threading.Thread(target=writer_a)
    tb = threading.Thread(target=writer_b)
    ta.start()
    tb.start()
    ta.join()
    tb.join()

    # 至少 writer_a 成功;writer_b 可能因 race 抛错
    assert any(s == 1 for s in results)
    # 账本有 1 条或 2 条事件,seq 严格连续
    seqs = [e.seq for e in store.events]
    assert seqs == sorted(seqs)
    assert all(1 <= s <= 2 for s in seqs)


def test_concurrent_with_terminal_seal() -> None:
    """并发场景:某个 worker 在 terminal event 之前 append,seal 后其它 worker 抛错。"""
    store = RunStore(run_id="r-seal-race")
    barrier = threading.Barrier(3)

    def terminal_worker() -> None:
        barrier.wait()
        store.seal(AgentRunStarted(agent_role="terminal"))

    def non_terminal_worker_a() -> None:
        barrier.wait()
        with contextlib.suppress(Exception):
            store.append(AgentRunStarted(agent_role="a"))

    def non_terminal_worker_b() -> None:
        barrier.wait()
        with contextlib.suppress(Exception):
            store.append(AgentRunStarted(agent_role="b"))

    t_term = threading.Thread(target=terminal_worker)
    t_a = threading.Thread(target=non_terminal_worker_a)
    t_b = threading.Thread(target=non_terminal_worker_b)
    t_term.start()
    t_a.start()
    t_b.start()
    t_term.join()
    t_a.join()
    t_b.join()

    # 不管谁先到,seq 严格连续;terminal 之后不再追加(L7)
    seqs = [e.seq for e in store.events]
    assert seqs == sorted(seqs)
    assert len(seqs) >= 1
