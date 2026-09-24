"""Tests for DesktopLockManager (ADR-0248 §5.3 / s13).

Invariants tested:
- INV-06: 单屏桌面互斥锁（allocateWindow / freeWindow）严格互斥，120s TTL 超时防死锁。
"""

import pytest

from lca.infrastructure.computer.desktop_lock import DesktopLockManager


@pytest.mark.asyncio
async def test_desktop_lock_mutual_exclusion_and_release():
    lock_mgr = DesktopLockManager(default_ttl_s=120)
    assert lock_mgr.is_locked() is False

    # 1. 第一个 agent 成功抢锁
    acquired = await lock_mgr.allocate_window(agent_id="sub_agent_1", session_id="sess_1")
    assert acquired is True
    assert lock_mgr.is_locked() is True
    assert lock_mgr.get_current_owner() == "sub_agent_1"

    # 2. 第二个 agent 争锁失败（互斥锁硬不变量）
    acquired_2 = await lock_mgr.allocate_window(agent_id="sub_agent_2", session_id="sess_1")
    assert acquired_2 is False
    assert lock_mgr.get_current_owner() == "sub_agent_1"

    # 3. 只有持有者本人能主动释放
    freed_fake = await lock_mgr.free_window(agent_id="sub_agent_2", session_id="sess_1")
    assert freed_fake is False
    assert lock_mgr.is_locked() is True

    # 4. 持有者释放后，第二个 agent 可成功加锁
    freed_real = await lock_mgr.free_window(agent_id="sub_agent_1", session_id="sess_1")
    assert freed_real is True
    assert lock_mgr.is_locked() is False

    acquired_2_retry = await lock_mgr.allocate_window(agent_id="sub_agent_2", session_id="sess_1")
    assert acquired_2_retry is True
    assert lock_mgr.get_current_owner() == "sub_agent_2"


@pytest.mark.asyncio
async def test_desktop_lock_ttl_expiration_prevents_deadlock():
    # 设置 1 秒短 TTL 测试超时防死锁
    lock_mgr = DesktopLockManager(default_ttl_s=1)
    acquired = await lock_mgr.allocate_window(agent_id="sub_crash", session_id="sess_crash")
    assert acquired is True

    # 模拟等待 1.1 秒后超时
    import asyncio

    await asyncio.sleep(1.1)

    # 虽然持有者未释放，但锁已超时，新 agent 应能成功夺得锁
    acquired_new = await lock_mgr.allocate_window(agent_id="sub_revive", session_id="sess_crash")
    assert acquired_new is True
    assert lock_mgr.get_current_owner() == "sub_revive"
