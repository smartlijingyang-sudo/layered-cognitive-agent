"""Tests for multi-tenant in-flight run deduplication isolation (INV-04)."""

from types import SimpleNamespace

from lca.plugins.transport.webserver.handlers.runs.session.index.index import (
    RunSessionIndex,
    run_dedup_key,
)


def test_multitenant_inflight_run_dedup_isolation():
    key_user_a = run_dedup_key(
        user_id="user_A",
        user_text="查上月华东区销售额",
        mode="solo",
        agent_id="asst_1",
    )
    key_user_b = run_dedup_key(
        user_id="user_B",
        user_text="查上月华东区销售额",
        mode="solo",
        agent_id="asst_1",
    )
    assert key_user_a != key_user_b


def test_multitenant_inflight_run_session_index_isolation():
    index = RunSessionIndex()
    session_a = SimpleNamespace(
        run_id="run_a",
        user_text="查上月华东区销售额",
        mode="solo",
        attachment_ids=(),
        agent=SimpleNamespace(agent_id="asst_1"),
        user_id="user_A",
        status=SimpleNamespace(value="running"),
    )

    index.put(session_a)

    # 1. 相同用户 A 发送相同提问，命中 In-flight 去重
    found_a = index.find_inflight_run(
        user_text="查上月华东区销售额",
        mode="solo",
        agent_id="asst_1",
        user_id="user_A",
    )
    assert found_a is not None
    assert found_a.run_id == "run_a"

    # 2. 不同用户 B 发送相同提问，绝不命中用户 A 的 In-flight 任务，严格隔离
    found_b = index.find_inflight_run(
        user_text="查上月华东区销售额",
        mode="solo",
        agent_id="asst_1",
        user_id="user_B",
    )
    assert found_b is None
